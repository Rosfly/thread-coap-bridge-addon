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

    async def observe_resource(self, device_id, ipv6_addr, uri_path):
        """
        Start CoAP Observe on a resource.
        Automatically publishes updates to MQTT.
        """
        logger.info(f"Starting observation: {device_id} - coap://[{ipv6_addr}]{uri_path}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return

        try:
            uri = f'coap://[{ipv6_addr}]{uri_path}'
            request = Message(code=GET, uri=uri, observe=0)

            # Start observation
            observation_request = self.context.request(request)

            # Store observation so we can cancel it later
            obs_key = f"{device_id}{uri_path}"
            self.observations[obs_key] = observation_request

            # Process observation responses
            async for response in observation_request.observation:
                if not self.running:
                    break

                if response.code.is_successful():
                    payload = response.payload.decode('utf-8')
                    logger.debug(f"Observe update from {device_id}{uri_path}: {payload}")

                    # Try to parse as JSON
                    try:
                        state_value = json.loads(payload)
                    except json.JSONDecodeError:
                        state_value = payload

                    # Publish state to MQTT
                    self.mqtt.publish_state(device_id, uri_path, state_value)
                else:
                    logger.warning(f"Observe response error: {response.code}")

        except asyncio.CancelledError:
            logger.info(f"Observation cancelled for {device_id}{uri_path}")
        except Exception as e:
            logger.error(f"Observe error for {device_id}{uri_path}: {e}")
        finally:
            # Clean up observation
            obs_key = f"{device_id}{uri_path}"
            if obs_key in self.observations:
                del self.observations[obs_key]

    async def poll_resource(self, device_id, ipv6_addr, uri_path, interval=5):
        """
        Poll a resource periodically (alternative to Observe for non-observable resources).
        """
        logger.info(f"Starting polling: {device_id} - coap://[{ipv6_addr}]{uri_path} (interval: {interval}s)")

        poll_key = f"{device_id}{uri_path}"

        while self.running:
            try:
                payload = await self.get_resource(ipv6_addr, uri_path)

                if payload:
                    try:
                        state_value = json.loads(payload)
                    except json.JSONDecodeError:
                        state_value = payload

                    self.mqtt.publish_state(device_id, uri_path, state_value)

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                logger.info(f"Polling cancelled for {device_id}{uri_path}")
                break
            except Exception as e:
                logger.error(f"Polling error for {device_id}{uri_path}: {e}")
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
