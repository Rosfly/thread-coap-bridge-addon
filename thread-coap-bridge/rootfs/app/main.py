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

    async def _discovery_loop(self):
        """Periodic discovery of new devices."""
        interval = self.config.get('discovery_interval', 60)

        logger.info(f"Starting discovery loop (interval: {interval}s)")

        while self.running:
            try:
                logger.debug("Running device discovery...")
                await self.discovery.discover_devices()
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
                        for resource in resources:
                            # Start polling (use polling instead of observe for now)
                            poll_task = asyncio.create_task(
                                self.coap_client.poll_resource(
                                    device.device_id,
                                    device.ipv6_address,
                                    resource.uri_path,
                                    interval=5
                                ),
                                name=f"poll_{device.device_id}_{resource.uri_path}"
                            )
                            self.tasks.append(poll_task)

                        # Mark as commissioned
                        await self.registry.mark_commissioned(device.device_id)

                        logger.info(f"Device {device.device_id} commissioned successfully")

                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"Error in device monitor: {e}")
                await asyncio.sleep(10)

    def _translate_mqtt_to_coap(self, resource, mqtt_payload):
        """Translate Home Assistant MQTT payload to device CoAP format."""
        try:
            # Parse MQTT JSON payload
            mqtt_data = json.loads(mqtt_payload)

            # Handle LED resource
            if resource == "led":
                # Home Assistant sends: {"state": "ON"} or {"state": "OFF"}
                # Device expects: {"led_id": 0, "state": 1} where 0=OFF, 1=ON, 2=TOGGLE
                state_str = mqtt_data.get("state", "OFF").upper()

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

            # For other resources, pass through as-is
            return mqtt_payload

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON payload: {mqtt_payload}")
            return None
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

            # Send CoAP PUT request
            success = await self.coap_client.put_resource(
                device.ipv6_address,
                uri_path,
                coap_payload
            )

            if success:
                logger.info(f"Successfully sent command to {device_id}{uri_path}")

                # Read back the state to update MQTT
                response = await self.coap_client.get_resource(device.ipv6_address, uri_path)
                if response:
                    try:
                        state_value = json.loads(response)
                    except json.JSONDecodeError:
                        state_value = response

                    self.mqtt.publish_state(device_id, uri_path, state_value)
            else:
                logger.warning(f"Failed to send command to {device_id}{uri_path}")

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
