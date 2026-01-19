"""
CoAP Client Module

Handles GET/PUT operations and CoAP Observe for real-time updates.
"""
import asyncio
import logging
import json
from aiocoap import Context, Message, GET, PUT, Code
from aiocoap.error import RequestTimedOut, Error

logger = logging.getLogger(__name__)


class CoAPClient:
    """CoAP client for device interaction."""

    def __init__(self, mqtt_publisher):
        self.mqtt = mqtt_publisher
        self.context = None
        self.observations = {}
        self.running = True

        logger.info("CoAP Client initialized")

    async def initialize(self):
        """Initialize CoAP context."""
        try:
            self.context = await Context.create_client_context()
            logger.info("CoAP client context initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CoAP context: {e}")
            raise

    async def get_resource(self, ipv6_addr, uri_path):
        """GET request to CoAP resource."""
        logger.debug(f"GET coap://[{ipv6_addr}]{uri_path}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return None

        try:
            uri = f'coap://[{ipv6_addr}]{uri_path}'
            request = Message(code=GET, uri=uri)

            response = await asyncio.wait_for(
                self.context.request(request).response,
                timeout=10.0
            )

            if response.code.is_successful():
                payload = response.payload.decode('utf-8')
                # Strip null terminators that firmware includes
                payload = payload.rstrip('\x00')
                logger.debug(f"GET response from {ipv6_addr}{uri_path}: {payload}")
                return payload
            else:
                logger.warning(f"GET failed with code {response.code}")
                return None

        except asyncio.TimeoutError:
            logger.warning(f"GET timeout for {ipv6_addr}{uri_path}")
            return None
        except Exception as e:
            logger.error(f"GET error for {ipv6_addr}{uri_path}: {e}")
            return None

    async def put_resource(self, ipv6_addr, uri_path, payload):
        """PUT request to CoAP resource (for control commands)."""
        logger.debug(f"PUT coap://[{ipv6_addr}]{uri_path} = {payload}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return False

        try:
            uri = f'coap://[{ipv6_addr}]{uri_path}'

            # Ensure payload is bytes
            if isinstance(payload, str):
                payload_bytes = payload.encode('utf-8')
            elif isinstance(payload, dict):
                payload_bytes = json.dumps(payload).encode('utf-8')
            else:
                payload_bytes = payload

            request = Message(code=PUT, uri=uri, payload=payload_bytes)

            response = await asyncio.wait_for(
                self.context.request(request).response,
                timeout=10.0
            )

            if response.code.is_successful():
                logger.info(f"PUT successful for {ipv6_addr}{uri_path}")
                return True
            else:
                logger.warning(f"PUT failed with code {response.code}")
                return False

        except asyncio.TimeoutError:
            logger.warning(f"PUT timeout for {ipv6_addr}{uri_path}")
            return False
        except Exception as e:
            logger.error(f"PUT error for {ipv6_addr}{uri_path}: {e}")
            return False

    async def observe_resource(self, device_id, ipv6_addr, uri_path,
                               registry=None, offline_threshold=5, discovery=None):
        """
        Start CoAP Observe on a resource with automatic reconnection.
        Automatically publishes updates to MQTT.

        Note: Device reboots are detected via uptime polling in main.py,
        which triggers reregister_observers() when uptime resets.

        Args:
            device_id: Device identifier
            ipv6_addr: IPv6 address
            uri_path: CoAP URI path
            registry: DeviceRegistry instance for updating last_seen
            offline_threshold: Number of consecutive failures before marking offline
            discovery: CoAPDiscovery instance to call forget_device() when observe stops
        """
        logger.info(f"Starting observation: {device_id} - coap://[{ipv6_addr}]{uri_path}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return

        obs_key = f"{device_id}{uri_path}"
        consecutive_failures = 0
        device_is_online = True
        max_reconnect_attempts = 10

        while self.running and consecutive_failures < max_reconnect_attempts:
            try:
                uri = f'coap://[{ipv6_addr}]{uri_path}'
                request = Message(code=GET, uri=uri, observe=0)

                # Start observation
                observation_request = self.context.request(request)

                # Store observation so we can cancel and restart it later
                self.observations[obs_key] = {
                    'request': observation_request,
                    'device_id': device_id,
                    'ipv6_addr': ipv6_addr,
                    'uri_path': uri_path,
                    'registry': registry,
                    'offline_threshold': offline_threshold,
                    'discovery': discovery
                }

                # Wait for initial response (with timeout)
                try:
                    initial_response = await asyncio.wait_for(
                        observation_request.response,
                        timeout=15.0
                    )

                    if initial_response.code.is_successful():
                        # Successfully established observation
                        consecutive_failures = 0

                        if registry:
                            await registry.update_device_failure(device_id, failed=False)

                        if not device_is_online:
                            logger.info(f"Device {device_id} back online (observe)")
                            self.mqtt.publish_availability(device_id, available=True)
                            device_is_online = True

                        # Process initial response
                        payload = initial_response.payload.decode('utf-8').rstrip('\x00')
                        logger.info(f"Observe established for {device_id}{uri_path}")
                        try:
                            state_value = json.loads(payload)
                        except json.JSONDecodeError:
                            state_value = payload
                        self.mqtt.publish_state(device_id, uri_path, state_value)

                    else:
                        logger.warning(f"Observe registration failed: {initial_response.code}")
                        consecutive_failures += 1
                        await asyncio.sleep(5)
                        continue

                except asyncio.TimeoutError:
                    logger.warning(f"Observe registration timeout for {device_id}{uri_path}")
                    consecutive_failures += 1

                    if consecutive_failures >= offline_threshold and device_is_online:
                        logger.warning(f"Device {device_id} marked offline (observe timeout)")
                        self.mqtt.publish_availability(device_id, available=False)
                        device_is_online = False
                        if registry:
                            await registry.mark_device_offline(device_id)

                    await asyncio.sleep(10)
                    continue

                # Process observation notifications
                # The async for loop blocks waiting for notifications from the server
                # It ends when: observation is cancelled, server sends deregister, or error
                try:
                    async for response in observation_request.observation:
                        if not self.running:
                            break

                        if response.code.is_successful():
                            payload = response.payload.decode('utf-8').rstrip('\x00')
                            logger.debug(f"Observe notification from {device_id}{uri_path}: {payload}")

                            # Reset failure counter on successful notification
                            consecutive_failures = 0
                            if registry:
                                await registry.update_device_failure(device_id, failed=False)

                            # Try to parse as JSON
                            try:
                                state_value = json.loads(payload)
                            except json.JSONDecodeError:
                                state_value = payload

                            # Publish state to MQTT
                            self.mqtt.publish_state(device_id, uri_path, state_value)
                        else:
                            logger.warning(f"Observe notification error: {response.code}")
                except Exception as obs_error:
                    logger.warning(f"Observation iteration error for {device_id}{uri_path}: {obs_error}")

                # Observation stream ended - wait before re-establishing
                # Device reboots are handled separately via uptime polling
                logger.info(f"Observe stream ended for {device_id}{uri_path}, waiting before retry...")
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info(f"Observation cancelled for {device_id}{uri_path}")
                break
            except Exception as e:
                logger.error(f"Observe error for {device_id}{uri_path}: {e}")
                consecutive_failures += 1

                if consecutive_failures >= offline_threshold and device_is_online:
                    logger.warning(f"Device {device_id} marked offline (observe error)")
                    self.mqtt.publish_availability(device_id, available=False)
                    device_is_online = False
                    if registry:
                        await registry.mark_device_offline(device_id)

                await asyncio.sleep(10)

        # Cleanup
        if obs_key in self.observations:
            del self.observations[obs_key]

        if consecutive_failures >= max_reconnect_attempts:
            logger.warning(f"Giving up observe for {device_id}{uri_path} after {consecutive_failures} failures")
            if discovery:
                discovery.forget_device(ipv6_addr)

    async def reregister_observers(self, device_id):
        """
        Re-register all observers for a device after detecting a reboot.
        Called by main.py when uptime reset is detected.
        """
        logger.info(f"Re-registering observers for {device_id} after reboot detected")

        # Find all observations for this device
        device_observations = [
            (key, obs) for key, obs in self.observations.items()
            if obs.get('device_id') == device_id
        ]

        for obs_key, obs_info in device_observations:
            try:
                # Cancel existing observation
                if 'request' in obs_info:
                    try:
                        obs_info['request'].observation.cancel()
                    except Exception:
                        pass

                # Remove from tracking
                del self.observations[obs_key]

                # Re-start observation (will be picked up by the while loop naturally)
                # Create a new task to restart the observation
                asyncio.create_task(
                    self.observe_resource(
                        obs_info['device_id'],
                        obs_info['ipv6_addr'],
                        obs_info['uri_path'],
                        registry=obs_info.get('registry'),
                        offline_threshold=obs_info.get('offline_threshold', 5),
                        discovery=obs_info.get('discovery')
                    ),
                    name=f"reobserve_{device_id}_{obs_info['uri_path']}"
                )
                logger.info(f"Re-started observation for {device_id}{obs_info['uri_path']}")

            except Exception as e:
                logger.error(f"Error re-registering observer {obs_key}: {e}")

    async def poll_resource(self, device_id, ipv6_addr, uri_path, interval=5,
                           registry=None, offline_threshold=5, stop_after_offline=30,
                           discovery=None, state_filter=None):
        """
        Poll a resource periodically with failure tracking.

        Args:
            device_id: Device identifier
            ipv6_addr: IPv6 address
            uri_path: CoAP URI path
            interval: Polling interval in seconds
            registry: DeviceRegistry instance for updating last_seen
            offline_threshold: Number of consecutive failures before marking offline
            stop_after_offline: Stop polling after this many failures beyond offline threshold
                               (let discovery find device with potentially new IP)
            discovery: CoAPDiscovery instance to call forget_device() when polling stops
            state_filter: Optional callback(device_id, resource, state_value) -> bool
                         Returns True if state should be published, False to suppress
        """
        logger.info(f"Starting polling: {device_id} - coap://[{ipv6_addr}]{uri_path} "
                    f"(interval: {interval}s, offline_threshold: {offline_threshold})")

        consecutive_failures = 0
        device_is_online = True
        max_failures = offline_threshold + stop_after_offline  # Stop polling after this many total failures

        while self.running:
            try:
                payload = await self.get_resource(ipv6_addr, uri_path)

                if payload:
                    # Success - reset failure counter
                    if consecutive_failures > 0:
                        logger.info(f"Device {device_id} back online after {consecutive_failures} failures")

                    consecutive_failures = 0

                    # Update last_seen in registry
                    if registry:
                        await registry.update_device_failure(device_id, failed=False)

                    # If device was offline, publish it as back online
                    if not device_is_online:
                        logger.info(f"Publishing {device_id} as online")
                        self.mqtt.publish_availability(device_id, available=True)
                        device_is_online = True

                    # Parse and publish state
                    try:
                        state_value = json.loads(payload)
                    except json.JSONDecodeError:
                        state_value = payload

                    # Check if state should be published (may be suppressed after recent command)
                    resource = uri_path.strip('/')
                    should_publish = True
                    if state_filter:
                        should_publish = state_filter(device_id, resource, state_value)

                    if should_publish:
                        self.mqtt.publish_state(device_id, uri_path, state_value)
                    else:
                        logger.debug(f"State update suppressed for {device_id}/{resource} (recent command)")

                else:
                    # Failure - increment counter
                    consecutive_failures += 1

                    if registry:
                        await registry.update_device_failure(device_id, failed=True)

                    logger.warning(f"Poll failed for {device_id}{uri_path} "
                                  f"({consecutive_failures}/{offline_threshold} failures)")

                    # Check if we've reached offline threshold
                    if consecutive_failures >= offline_threshold and device_is_online:
                        logger.warning(f"Device {device_id} marked as offline after "
                                      f"{consecutive_failures} consecutive failures")

                        # Publish offline availability
                        self.mqtt.publish_availability(device_id, available=False)
                        device_is_online = False

                        # Mark in database
                        if registry:
                            await registry.mark_device_offline(device_id)

                        # Allow re-discovery immediately (don't wait for max_failures)
                        if discovery:
                            discovery.forget_device(ipv6_addr)

                    # Stop polling after too many failures - let discovery find device again
                    if consecutive_failures >= max_failures:
                        logger.info(f"Stopping poll for {device_id}{uri_path} after {consecutive_failures} failures. "
                                   f"Discovery will find device if it comes back online.")
                        # Remove from discovered_addresses so it can be re-registered
                        if discovery:
                            discovery.forget_device(ipv6_addr)
                        break

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info(f"Polling cancelled for {device_id}{uri_path}")
                break
            except Exception as e:
                logger.error(f"Polling error for {device_id}{uri_path}: {e}")
                consecutive_failures += 1

                if registry:
                    await registry.update_device_failure(device_id, failed=True)

                # Also check max failures on exceptions
                if consecutive_failures >= max_failures:
                    logger.info(f"Stopping poll for {device_id}{uri_path} after {consecutive_failures} failures.")
                    # Remove from discovered_addresses so it can be re-registered
                    if discovery:
                        discovery.forget_device(ipv6_addr)
                    break

                await asyncio.sleep(interval)

    async def shutdown(self):
        """Cleanup and close connections."""
        logger.info("Shutting down CoAP client")

        self.running = False

        # Cancel all observations
        for obs_key, observation in list(self.observations.items()):
            try:
                observation.observation.cancel()
                logger.debug(f"Cancelled observation: {obs_key}")
            except Exception as e:
                logger.error(f"Error cancelling observation {obs_key}: {e}")

        self.observations.clear()

        # Close context
        if self.context:
            await self.context.shutdown()
            logger.info("CoAP client context shut down")
