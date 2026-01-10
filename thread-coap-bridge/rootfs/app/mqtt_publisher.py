"""
MQTT Publisher Module

Handles Home Assistant MQTT Discovery and state publishing.
"""
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """MQTT publisher for Home Assistant integration."""

    def __init__(self, mqtt_config):
        self.host = mqtt_config['host']
        self.port = mqtt_config['port']
        self.username = mqtt_config.get('username', '')
        self.password = mqtt_config.get('password', '')
        self.client = None
        self.discovery_prefix = "homeassistant"
        self.connected = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.loop = None  # Will be set in connect()

        logger.info(f"MQTT Publisher initialized (broker: {self.host}:{self.port})")

    async def connect(self):
        """Connect to MQTT broker."""
        logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}")

        try:
            # Store event loop reference for callback thread
            self.loop = asyncio.get_event_loop()

            # Initialize paho-mqtt client
            self.client = mqtt.Client(client_id="thread_coap_bridge", protocol=mqtt.MQTTv311)

            # Set username/password if provided (only if username is not empty)
            if self.username and self.username.strip():
                logger.info(f"Setting MQTT credentials for user: {self.username}")
                self.client.username_pw_set(self.username, self.password)
            else:
                logger.info("Connecting to MQTT without authentication")

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Connect to broker
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.client.connect(self.host, self.port, keepalive=60)
            )

            # Start network loop in background
            self.client.loop_start()

            # Wait for connection
            await asyncio.sleep(2)

            if self.connected:
                logger.info("Successfully connected to MQTT broker")
            else:
                logger.warning("MQTT connection status uncertain")

            # Subscribe to command topics (for LED control from HA)
            self.client.subscribe("thread/+/+/set")
            logger.info("Subscribed to command topics: thread/+/+/set")

        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")
            raise

    async def disconnect(self):
        """Disconnect from MQTT broker."""
        logger.info("Disconnecting from MQTT broker")

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

        self.executor.shutdown(wait=True)
        logger.info("MQTT client disconnected")

    def publish_discovery(self, device_id, resource_type, resource_uri, ipv6_addr):
        """
        Publish Home Assistant MQTT Discovery message.

        Topic format: homeassistant/<component>/<node_id>/<object_id>/config
        """
        logger.info(f"Publishing discovery: {device_id}/{resource_uri} ({resource_type})")

        # Map resource type to HA component
        component = self._map_resource_to_component(resource_type)

        # Clean resource URI for use in topic
        object_id = resource_uri.strip('/')

        # Build discovery topic
        topic = f"{self.discovery_prefix}/{component}/{device_id}/{object_id}/config"

        # Build state and command topics
        state_topic = f"thread/{device_id}/{object_id}/state"
        command_topic = f"thread/{device_id}/{object_id}/set"
        availability_topic = f"thread/{device_id}/availability"

        # Build discovery payload based on component type
        payload = {
            "name": f"{device_id} {object_id}",
            "unique_id": f"{device_id}_{object_id}",
            "state_topic": state_topic,
            "availability_topic": availability_topic,
            "device": {
                "identifiers": [device_id],
                "name": f"Thread Device {device_id}",
                "manufacturer": "Thread CoAP Device",
                "model": "nRF54L15",
                "sw_version": "1.0.0"
            }
        }

        # Add component-specific configuration
        if component == "light":
            payload["command_topic"] = command_topic
            payload["payload_on"] = json.dumps({"led_id": 0, "state": 1})
            payload["payload_off"] = json.dumps({"led_id": 0, "state": 0})
            payload["state_on"] = "1"
            payload["state_off"] = "0"
            payload["optimistic"] = False
            payload["schema"] = "json"

        elif component == "binary_sensor":
            payload["payload_on"] = "0"  # GPIO_ACTIVE_LOW: 0 = pressed
            payload["payload_off"] = "1"  # 1 = not pressed
            # Don't set device_class for buttons - HA doesn't have a "button" class for binary_sensor
            # The entity will appear as a generic binary_sensor

        elif component == "sensor":
            payload["unit_of_measurement"] = self._get_unit_for_sensor(resource_type)

        # Publish discovery message with retain flag
        payload_json = json.dumps(payload)
        result = self.client.publish(topic, payload_json, qos=1, retain=True)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published discovery to {topic}")
        else:
            logger.error(f"Failed to publish discovery: {result.rc}")

    def publish_state(self, device_id, resource_uri, state_value):
        """Publish device state update."""
        object_id = resource_uri.strip('/')
        state_topic = f"thread/{device_id}/{object_id}/state"

        logger.debug(f"Publishing state: {state_topic} = {state_value}")

        # Handle different state value types
        if isinstance(state_value, dict):
            # For complex JSON responses (like button state with multiple buttons)
            # Extract the relevant state value
            if 'state' in state_value:
                payload = str(state_value['state'])
            elif 'btns' in state_value and len(state_value['btns']) > 0:
                # For button: extract first button state
                payload = str(state_value['btns'][0]['state'])
            else:
                payload = json.dumps(state_value)
        else:
            payload = str(state_value)

        result = self.client.publish(state_topic, payload, qos=1, retain=False)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish state: {result.rc}")

    def publish_availability(self, device_id, available=True):
        """Publish device availability."""
        avail_topic = f"thread/{device_id}/availability"
        payload = "online" if available else "offline"

        logger.info(f"Publishing availability: {device_id} = {payload}")

        result = self.client.publish(avail_topic, payload, qos=1, retain=True)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish availability: {result.rc}")

    def set_command_callback(self, callback):
        """Set callback for MQTT command messages (LED control from HA)."""
        self._command_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            logger.info("MQTT connection established")
            self.connected = True
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.connected = False

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        logger.warning(f"MQTT disconnected with code {rc}")
        self.connected = False

    def _on_message(self, client, userdata, msg):
        """MQTT message callback for command topics."""
        logger.debug(f"Received MQTT message: {msg.topic} = {msg.payload}")

        try:
            # Parse topic: thread/<device_id>/<resource>/set
            parts = msg.topic.split('/')
            if len(parts) >= 4 and parts[0] == 'thread' and parts[3] == 'set':
                device_id = parts[1]
                resource = parts[2]
                payload = msg.payload.decode('utf-8')

                # Call command callback if set
                if hasattr(self, '_command_callback') and self._command_callback:
                    # Schedule coroutine on main event loop from MQTT thread
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(
                            self._command_callback(device_id, resource, payload),
                            self.loop
                        )

        except Exception as e:
            logger.error(f"Error processing MQTT command: {e}")

    def _map_resource_to_component(self, resource_type):
        """Map CoAP resource type to Home Assistant component."""
        mapping = {
            "light": "light",
            "led": "light",
            "switch": "switch",
            "button": "binary_sensor",
            "battery": "sensor",
            "temperature": "sensor",
            "humidity": "sensor"
        }
        return mapping.get(resource_type.lower(), "sensor")

    def _get_unit_for_sensor(self, resource_type):
        """Get unit of measurement for sensor types."""
        units = {
            "temperature": "°C",
            "humidity": "%",
            "battery": "%",
            "voltage": "V",
            "current": "A"
        }
        return units.get(resource_type.lower(), None)
