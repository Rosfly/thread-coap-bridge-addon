#!/usr/bin/env python3
"""
Thread CoAP to MQTT Bridge - Main Entry Point

This service bridges CoAP devices on Thread networks to Home Assistant via MQTT.
"""
import asyncio
import signal
import sys
import logging
import json
import time
from config_handler import ConfigHandler
from device_registry import DeviceRegistry
from mqtt_publisher import MQTTPublisher
from coap_discovery import CoAPDiscovery
from coap_client import CoAPClient

logger = logging.getLogger(__name__)


class CoAPBridgeService:
    """Main bridge service orchestrator."""

    def __init__(self):
        self.config = ConfigHandler()
        self.running = True

        # Components
        self.registry = None
        self.mqtt = None
        self.discovery = None
        self.coap_client = None

        # Background tasks
        self.tasks = []

        # Track recent commands to suppress poll updates temporarily
        # Format: {(device_id, resource): (timestamp, expected_state)}
        self.recent_commands = {}
        self.command_suppress_time = 10  # Seconds to suppress poll updates after command

        # Track device uptime to detect reboots
        # Format: {device_id: last_uptime_ms}
        self.device_uptimes = {}

        # Track per-sensor failures for availability reporting
        # Format: {(device_id, uri_path): consecutive_failure_count}
        self.sensor_failures = {}
        # Format: {(device_id, uri_path): is_available}
        self.sensor_available = {}
        # Number of consecutive failures before marking sensor offline
        self.sensor_offline_threshold = 3

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        logger.info("CoAP Bridge Service initialized")

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on SIGTERM/SIGINT."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    async def start(self):
        """Start the bridge service."""
        logger.info("=" * 60)
        logger.info("Starting Thread CoAP-MQTT Bridge")
        logger.info("=" * 60)

        # Display configuration
        logger.info("Configuration:")
        logger.info(f"  MQTT Host: {self.config.get('mqtt_host')}")
        logger.info(f"  MQTT Port: {self.config.get('mqtt_port')}")
        logger.info(f"  Discovery Interval: {self.config.get('discovery_interval')}s")
        logger.info(f"  Thread Interface: {self.config.get('thread_interface')}")
        logger.info(f"  Multicast Address: {self.config.get('multicast_address')}")

        try:
            # Initialize device registry
            logger.info("Initializing device registry...")
            self.registry = DeviceRegistry(db_path='/data/devices.db')
            await self.registry.initialize()

            # Initialize MQTT client
            logger.info("Connecting to MQTT broker...")
            self.mqtt = MQTTPublisher(self.config.mqtt_config)
            await self.mqtt.connect()

            # Set MQTT command callback for LED control from HA
            self.mqtt.set_command_callback(self._handle_mqtt_command)

            # Initialize CoAP client
            logger.info("Initializing CoAP client...")
            self.coap_client = CoAPClient(self.mqtt)
            await self.coap_client.initialize()

            # Initialize CoAP discovery
            logger.info("Initializing CoAP discovery...")
            self.discovery = CoAPDiscovery(self.registry, self.config.coap_config)
            await self.discovery.initialize()

            # Re-publish MQTT discovery for all known devices on startup
            # This ensures HA has up-to-date discovery config after addon updates
            await self._republish_all_discovery()

            # Start background tasks
            logger.info("Starting background tasks...")

            # Task 1: Periodic discovery
            discovery_task = asyncio.create_task(
                self._discovery_loop(),
                name="discovery_loop"
            )
            self.tasks.append(discovery_task)

            # Task 2: Monitor and commission devices
            monitor_task = asyncio.create_task(
                self._monitor_devices(),
                name="device_monitor"
            )
            self.tasks.append(monitor_task)

            # Task 3: Cleanup offline devices periodically
            cleanup_task = asyncio.create_task(
                self._cleanup_loop(),
                name="cleanup_loop"
            )
            self.tasks.append(cleanup_task)

            logger.info("=" * 60)
            logger.info("Service started successfully")
            logger.info("Bridge is now running - monitoring for CoAP devices...")
            logger.info("=" * 60)

            # Keep service running
            while self.running:
                await asyncio.sleep(1)

            logger.info("Shutdown initiated...")

            # Cleanup
            await self._cleanup()

        except Exception as e:
            logger.exception(f"Fatal error in main loop: {e}")
            sys.exit(1)

    async def _republish_all_discovery(self):
        """Re-publish MQTT discovery for all known devices on startup."""
        logger.info("Re-publishing MQTT discovery for all known devices...")

        try:
            all_devices = await self.registry.get_all_devices()
            for device in all_devices:
                resources = await self.registry.get_device_resources(device.device_id)
                logger.info(f"Re-publishing discovery for {device.device_id} ({len(resources)} resources)")

                for resource in resources:
                    self.mqtt.publish_discovery(
                        device.device_id,
                        resource.resource_type,
                        resource.uri_path,
                        device.ipv6_address
                    )

                # Also publish availability
                is_online = getattr(device, 'is_online', True)
                self.mqtt.publish_availability(device.device_id, available=is_online)

            logger.info(f"Re-published discovery for {len(all_devices)} devices")

        except Exception as e:
            logger.error(f"Error re-publishing discovery: {e}")

    async def _discovery_loop(self):
        """Periodic discovery of new devices."""
        interval = self.config.get('discovery_interval', 60)

        logger.info(f"Starting discovery loop (interval: {interval}s)")

        while self.running:
            try:
                logger.debug("Running device discovery...")
                await self.discovery.discover_devices()
                # Also try unicast rediscovery for known offline devices
                # This bypasses broken aiocoap multicast on Thread/wpan0
                await self.discovery.rediscover_offline_devices(self.registry)
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in discovery loop: {e}")
                await asyncio.sleep(interval)

    async def _monitor_devices(self):
        """Monitor registered devices and commission new ones."""
        logger.info("Starting device monitor")

        while self.running:
            try:
                # Check for uncommissioned devices
                uncommissioned = await self.registry.get_uncommissioned_devices()

                for device in uncommissioned:
                    logger.info(f"Found uncommissioned device: {device.device_id}")

                    # Get device resources
                    resources = await self.registry.get_device_resources(device.device_id)
                    logger.info(f"Retrieved {len(resources)} resources from database for {device.device_id}")

                    if resources:
                        # Publish MQTT Discovery for each resource
                        for resource in resources:
                            logger.info(f"  Publishing discovery for {resource.uri_path} (type: {resource.resource_type})")

                            # For button resources, query to see how many buttons exist
                            if resource.resource_type == "button":
                                try:
                                    response = await self.coap_client.get_resource(
                                        device.ipv6_address,
                                        resource.uri_path
                                    )
                                    if response:
                                        btn_data = json.loads(response)
                                        if 'btns' in btn_data:
                                            # Create separate discovery for each button
                                            for btn in btn_data['btns']:
                                                btn_id = btn.get('btn_id', 0)
                                                btn_uri = f"{resource.uri_path}{btn_id}"
                                                logger.info(f"    Publishing discovery for button {btn_id}")
                                                self.mqtt.publish_discovery(
                                                    device.device_id,
                                                    resource.resource_type,
                                                    btn_uri,
                                                    device.ipv6_address
                                                )
                                            continue  # Skip the default publish below
                                except Exception as e:
                                    logger.warning(f"Could not query button count: {e}")

                            # Default: publish single resource
                            self.mqtt.publish_discovery(
                                device.device_id,
                                resource.resource_type,
                                resource.uri_path,
                                device.ipv6_address
                            )

                        # Publish device availability
                        self.mqtt.publish_availability(device.device_id, available=True)

                        # Start monitoring resources
                        # Use Observe for LED and button (real-time updates)
                        # Use polling for battery/voltage/uptime (slow-changing values)
                        offline_threshold = self.config.get('offline_threshold_polls', 5)

                        for resource in resources:
                            if resource.resource_type in ('led', 'button'):
                                # Use CoAP Observe for real-time updates
                                observe_task = asyncio.create_task(
                                    self.coap_client.observe_resource(
                                        device.device_id,
                                        device.ipv6_address,
                                        resource.uri_path,
                                        registry=self.registry,
                                        offline_threshold=offline_threshold,
                                        discovery=self.discovery
                                    ),
                                    name=f"observe_{device.device_id}_{resource.uri_path}"
                                )
                                self.tasks.append(observe_task)
                                logger.info(f"Started Observe for {device.device_id}/{resource.uri_path}")
                            else:
                                # Use staggered polling for sensors (battery, voltage, uptime)
                                # Staggering ensures battery is queried first (voltage depends on it)
                                # and reduces burst load on SED parent router
                                poll_delays = {
                                    'battery': 0,    # Battery first (voltage depends on fresh measurement)
                                    'voltage': 40,   # Voltage 40s after battery
                                    'uptime': 80,    # Uptime 80s after battery
                                }
                                initial_delay = poll_delays.get(resource.resource_type, 0)

                                poll_task = asyncio.create_task(
                                    self._poll_sensor(
                                        device.device_id,
                                        device.ipv6_address,
                                        resource.uri_path,
                                        resource.resource_type,
                                        interval=120,  # 120s interval for SED efficiency
                                        initial_delay=initial_delay
                                    ),
                                    name=f"poll_{device.device_id}_{resource.uri_path}"
                                )
                                self.tasks.append(poll_task)
                                logger.info(f"Started polling for {device.device_id}/{resource.uri_path} "
                                          f"(delay={initial_delay}s, interval=120s)")

                        # Mark as commissioned
                        await self.registry.mark_commissioned(device.device_id)

                        logger.info(f"Device {device.device_id} commissioned successfully")

                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"Error in device monitor: {e}")
                await asyncio.sleep(10)

    async def _cleanup_loop(self):
        """Background task to cleanup devices offline for extended period."""
        cleanup_interval = self.config.get('cleanup_check_interval', 3600)  # Check hourly
        cleanup_threshold_hours = self.config.get('cleanup_after_hours', 24)

        logger.info(f"Starting cleanup loop (check interval: {cleanup_interval}s, "
                    f"cleanup after: {cleanup_threshold_hours}h)")

        while self.running:
            try:
                # Wait for next cleanup check
                await asyncio.sleep(cleanup_interval)

                logger.debug("Running device cleanup check...")

                # Get devices eligible for cleanup
                devices_to_cleanup = await self.registry.get_devices_for_cleanup(
                    offline_hours=cleanup_threshold_hours
                )

                if devices_to_cleanup:
                    logger.info(f"Found {len(devices_to_cleanup)} devices to cleanup")

                    for device in devices_to_cleanup:
                        logger.info(f"Cleaning up device {device.device_id} "
                                   f"(offline since {device.last_seen})")

                        # Publish empty discovery to remove from Home Assistant
                        # (empty payload removes the entity)
                        resources = await self.registry.get_device_resources(device.device_id)
                        for resource in resources:
                            # Publish empty discovery config to remove
                            component = self.mqtt._map_resource_to_component(resource.resource_type)
                            object_id = resource.uri_path.strip('/')
                            topic = f"{self.mqtt.discovery_prefix}/{component}/{device.device_id}/{object_id}/config"

                            # Empty payload removes entity from HA
                            self.mqtt.client.publish(topic, "", qos=1, retain=True)
                            logger.debug(f"Removed discovery for {device.device_id}/{object_id}")

                        # Decommission device from registry
                        await self.registry.decommission_device(device.device_id)

                        logger.info(f"Device {device.device_id} cleaned up successfully")
                else:
                    logger.debug("No devices need cleanup")

            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(cleanup_interval)
    async def _poll_sensor(self, device_id, ipv6_addr, uri_path, resource_type,
                           interval=120, initial_delay=0):
        """
        Poll sensor resource with retry logic and per-sensor availability tracking.

        Args:
            device_id: Device identifier
            ipv6_addr: Device IPv6 address
            uri_path: CoAP resource path (e.g., /battery)
            resource_type: Type of sensor (battery, voltage, uptime)
            interval: Polling interval in seconds (default 120s for SED efficiency)
            initial_delay: Stagger start time to avoid simultaneous requests
        """
        sensor_key = (device_id, uri_path)
        object_id = uri_path.strip('/')

        logger.info(f"Starting sensor polling for {device_id}{uri_path} "
                   f"(interval: {interval}s, initial_delay: {initial_delay}s)")

        # Initialize availability tracking
        self.sensor_failures[sensor_key] = 0
        self.sensor_available[sensor_key] = True

        # Apply initial delay for staggered polling
        if initial_delay > 0:
            logger.info(f"Waiting {initial_delay}s before first poll of {uri_path}")
            await asyncio.sleep(initial_delay)

        poll_count = 0

        while self.running:
            try:
                poll_count += 1
                logger.info(f"Polling {uri_path} (#{poll_count})")

                # First attempt
                payload = await self.coap_client.get_resource(ipv6_addr, uri_path)

                # Retry once on failure (10s delay for SED to wake)
                if not payload:
                    logger.info(f"Retrying {uri_path} after 10s...")
                    await asyncio.sleep(10)
                    payload = await self.coap_client.get_resource(ipv6_addr, uri_path)

                if payload:
                    try:
                        data = json.loads(payload)
                        value = data.get('value', 0)

                        # Reset failure counter on success
                        if self.sensor_failures[sensor_key] > 0:
                            logger.info(f"Sensor {uri_path} recovered after "
                                       f"{self.sensor_failures[sensor_key]} failures")
                        self.sensor_failures[sensor_key] = 0

                        # Mark sensor online if it was offline
                        if not self.sensor_available.get(sensor_key, True):
                            self.sensor_available[sensor_key] = True
                            self.mqtt.publish_sensor_availability(device_id, object_id, True)
                            logger.info(f"Sensor {device_id}/{object_id} is back online")

                        # Special handling per resource type
                        if resource_type == 'uptime':
                            # Detect reboots
                            last_uptime = self.device_uptimes.get(device_id)
                            if last_uptime is not None and value < last_uptime:
                                logger.warning(f"Device {device_id} rebooted! "
                                             f"Uptime went from {last_uptime}ms to {value}ms")
                                # Re-register observers for this device
                                await self.coap_client.reregister_observers(device_id)

                            self.device_uptimes[device_id] = value
                            # Convert ms to seconds for display
                            value = value // 1000

                        elif resource_type == 'voltage':
                            # Convert millivolts to volts with proper formatting (4064 -> "4.06")
                            value = f"{value / 1000:.2f}"

                        logger.info(f"Sensor {uri_path}: {value}")
                        self.mqtt.publish_state(device_id, uri_path, {'value': value})

                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Failed to parse sensor response for {uri_path}: {e}")
                        self._handle_sensor_failure(device_id, uri_path, object_id)
                else:
                    logger.warning(f"No response from {uri_path} after retry (#{poll_count})")
                    self._handle_sensor_failure(device_id, uri_path, object_id)

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info(f"Sensor polling cancelled for {device_id}{uri_path}")
                break
            except Exception as e:
                logger.error(f"Error polling sensor {uri_path}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                self._handle_sensor_failure(device_id, uri_path, object_id)
                await asyncio.sleep(interval)

    def _handle_sensor_failure(self, device_id, uri_path, object_id):
        """Handle sensor polling failure - track consecutive failures and update availability."""
        sensor_key = (device_id, uri_path)
        self.sensor_failures[sensor_key] = self.sensor_failures.get(sensor_key, 0) + 1
        failure_count = self.sensor_failures[sensor_key]

        logger.warning(f"Sensor {uri_path} failure #{failure_count}")

        # Mark sensor offline after threshold consecutive failures
        if failure_count >= self.sensor_offline_threshold:
            if self.sensor_available.get(sensor_key, True):
                self.sensor_available[sensor_key] = False
                self.mqtt.publish_sensor_availability(device_id, object_id, False)
                logger.warning(f"Sensor {device_id}/{object_id} marked offline "
                             f"after {failure_count} consecutive failures")

    def _extract_led_state(self, state_value):
        """Extract LED state from various response formats."""
        if isinstance(state_value, dict):
            # Format: {"leds": [{"led_id": 0, "state": 1}]}
            if 'leds' in state_value and len(state_value['leds']) > 0:
                return state_value['leds'][0].get('state')
            # Format: {"state": 1}
            if 'state' in state_value:
                return state_value['state']
        return None

    def _should_publish_state(self, device_id, resource, state_value):
        """
        Check if a polled state should be published to MQTT.
        Returns False to suppress updates shortly after a user command (prevents UI flickering).
        """
        key = (device_id, resource)
        if key in self.recent_commands:
            cmd_time, expected_state = self.recent_commands[key]
            elapsed = time.time() - cmd_time

            if elapsed < self.command_suppress_time:
                # Still within suppression window - check if state matches expected
                actual_state = self._extract_led_state(state_value)

                if actual_state == expected_state:
                    # Device has confirmed the expected state - clear suppression
                    logger.info(f"Device confirmed state {expected_state} for {device_id}/{resource}")
                    del self.recent_commands[key]
                    return True
                else:
                    # State doesn't match yet - suppress this update
                    logger.debug(f"Suppressing poll update for {device_id}/{resource} "
                                f"(expected={expected_state}, actual={actual_state}, elapsed={elapsed:.1f}s)")
                    return False
            else:
                # Suppression window expired - publish real state and clear
                logger.info(f"Command suppression expired for {device_id}/{resource}, publishing real state")
                del self.recent_commands[key]
                return True

        return True

    def _translate_mqtt_to_coap(self, resource, mqtt_payload):
        """Translate Home Assistant MQTT payload to device CoAP format."""
        try:
            # Handle LED resource
            if resource == "led":
                # Home Assistant sends: "ON" or "OFF" (basic schema, no JSON)
                # Device expects: {"led_id": 0, "state": 1} where 0=OFF, 1=ON, 2=TOGGLE
                state_str = mqtt_payload.strip().upper()

                if state_str == "ON":
                    state_num = 1
                elif state_str == "OFF":
                    state_num = 0
                elif state_str == "TOGGLE":
                    state_num = 2
                else:
                    logger.warning(f"Unknown LED state: {state_str}")
                    return None

                return {"led_id": 0, "state": state_num}

            # For other resources, try to parse as JSON first, else pass through
            try:
                return json.loads(mqtt_payload)
            except json.JSONDecodeError:
                return mqtt_payload

        except Exception as e:
            logger.error(f"Error translating MQTT to CoAP: {e}")
            return None

    async def _handle_mqtt_command(self, device_id, resource, payload):
        """Handle MQTT commands from Home Assistant (e.g., LED control)."""
        logger.info(f"Received MQTT command: {device_id}/{resource} = {payload}")

        try:
            # Get device from registry
            device = await self.registry.get_device_by_id(device_id)

            if not device:
                logger.warning(f"Device {device_id} not found in registry")
                return

            # Build CoAP URI
            uri_path = f"/{resource}"

            # Translate Home Assistant MQTT payload to device-specific format
            coap_payload = self._translate_mqtt_to_coap(resource, payload)
            if not coap_payload:
                logger.warning(f"Could not translate MQTT payload: {payload}")
                return

            # For LED commands, immediately publish expected state (optimistic update)
            # This prevents UI flickering while waiting for device response
            if resource == "led" and isinstance(coap_payload, dict) and 'state' in coap_payload:
                expected_state = coap_payload['state']
                # Record this command to suppress poll updates temporarily
                self.recent_commands[(device_id, resource)] = (time.time(), expected_state)
                # Immediately publish expected state to MQTT
                self.mqtt.publish_state(device_id, uri_path, {'state': expected_state})
                logger.info(f"Published optimistic state for {device_id}/{resource}: {expected_state}")

            # Send CoAP PUT request
            success = await self.coap_client.put_resource(
                device.ipv6_address,
                uri_path,
                coap_payload
            )

            if success:
                logger.info(f"Successfully sent command to {device_id}{uri_path}")
                # Don't read back immediately - let the suppression window handle it
                # The next poll cycle after suppression will get the real state
            else:
                logger.warning(f"Failed to send command to {device_id}{uri_path}")
                # Command failed - clear the suppression so poll can update with real state
                self.recent_commands.pop((device_id, resource), None)

        except Exception as e:
            logger.error(f"Error handling MQTT command: {e}")

    async def _cleanup(self):
        """Cleanup tasks and connections."""
        logger.info("Cleaning up...")

        # Cancel all background tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Shutdown components
        if self.coap_client:
            await self.coap_client.shutdown()

        if self.discovery:
            await self.discovery.shutdown()

        if self.mqtt:
            await self.mqtt.disconnect()

        if self.registry:
            await self.registry.close()

        logger.info("Cleanup complete")


def main():
    """Main entry point."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

    try:
        logger.info("Initializing Thread CoAP Bridge...")
        service = CoAPBridgeService()
        asyncio.run(service.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
