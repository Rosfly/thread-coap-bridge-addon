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

            # Initialize paho-mqtt client with unique ID to avoid session conflicts
            import time
            client_id = f"thread_coap_bridge_{int(time.time())}"
            self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
            logger.info(f"MQTT client ID: {client_id}")

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
            # Use basic schema (not JSON) - simpler state handling
            # State: "ON" or "OFF" as strings
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
            payload["state_value_template"] = "{{ 'ON' if value == '1' else 'OFF' }}"
            payload["optimistic"] = False

        elif component == "binary_sensor":
            # Firmware uses gpio_pin_get_dt() which handles GPIO_ACTIVE_LOW automatically
            # So it returns: 1 = pressed/active, 0 = not pressed/inactive
            payload["payload_on"] = "1"   # 1 = button pressed
            payload["payload_off"] = "0"  # 0 = button not pressed
            # Don't set device_class for buttons - HA doesn't have a "button" class for binary_sensor
            # The entity will appear as a generic binary_sensor

        elif component == "sensor":
            unit = self._get_unit_for_sensor(resource_type)
            if unit:
                payload["unit_of_measurement"] = unit

            # Set device_class for proper HA display
            resource_lower = resource_type.lower()
            if resource_lower == "battery":
                payload["device_class"] = "battery"
                #payload["state_class"] = "measurement"
            #elif resource_lower == "voltage":
                #payload["device_class"] = "voltage"
                #payload["state_class"] = "measurement"
            elif resource_lower == "uptime":
                payload["device_class"] = "duration"
                payload["state_class"] = "total_increasing"

            # Use per-sensor availability for polled sensors (more accurate status)
            if resource_lower in ("battery", "voltage", "uptime"):
                payload["availability_topic"] = f"thread/{device_id}/{object_id}/availability"

        # Publish discovery message with retain flag
        payload_json = json.dumps(payload)
        logger.debug(f"Discovery payload: {payload_json}")

        try:
            result = self.client.publish(topic, payload_json, qos=1, retain=True)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Failed to queue discovery: {result.rc}")
                return

            # Wait for delivery confirmation
            result.wait_for_publish(timeout=5.0)

            if result.is_published():
                logger.info(f"Published discovery to {topic} (state_topic: {state_topic})")
            else:
                logger.warning(f"Discovery to {topic} may not have been delivered")

        except Exception as e:
            logger.error(f"Exception publishing discovery to {topic}: {e}")

    def publish_state(self, device_id, resource_uri, state_value):
        """Publish device state update."""
        object_id = resource_uri.strip('/')

        logger.info(f"publish_state called: device={device_id}, uri={resource_uri}, value={state_value} (type={type(state_value).__name__})")

        # Handle different state value types
        if isinstance(state_value, dict):
            # Check if this is a multi-button response
            if 'btns' in state_value and len(state_value['btns']) > 0:
                # Publish separate state for each button
                for btn in state_value['btns']:
                    btn_id = btn.get('btn_id', 0)
                    btn_state = str(btn.get('state', 0))
                    btn_topic = f"thread/{device_id}/{object_id}{btn_id}/state"
                    logger.debug(f"Publishing button state: {btn_topic} = {btn_state}")
                    result = self.client.publish(btn_topic, btn_state, qos=1, retain=False)
                    if result.rc != mqtt.MQTT_ERR_SUCCESS:
                        logger.error(f"Failed to publish button state: {result.rc}")
                return  # Done - published all buttons

            # For LED array response: {"device_id": "...", "leds": [{"led_id": 0, "state": 1}]}
            elif 'leds' in state_value and len(state_value['leds']) > 0:
                led_state = state_value['leds'][0].get('state', 0)
                payload = str(led_state)
                logger.info(f"LED state extracted from array: {led_state} -> payload='{payload}'")

            # For simple state response: {"state": 1}
            elif 'state' in state_value:
                state_val = state_value['state']
                payload = str(state_val)
                logger.info(f"LED state extracted: {state_val} -> payload='{payload}'")

            # For simple value response: {"device_id": "...", "value": 70}
            elif 'value' in state_value:
                raw_value = state_value['value']
                payload = str(raw_value)
                logger.info(f"Value extracted: {raw_value} -> payload='{payload}'")
            else:
                payload = json.dumps(state_value)
        else:
            payload = str(state_value)

        # Publish single state (retain=True so HA remembers state across restarts)
        state_topic = f"thread/{device_id}/{object_id}/state"

        if not self.connected:
            logger.error(f"MQTT not connected! Cannot publish to {state_topic}")
            return

        logger.info(f"Publishing state: {state_topic} = {payload}")

        try:
            result = self.client.publish(state_topic, payload, qos=1, retain=True)

            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Failed to queue publish to {state_topic}: rc={result.rc}")
                return

            # Wait for message to be delivered (important for QoS 1)
            result.wait_for_publish(timeout=5.0)

            if result.is_published():
                logger.debug(f"Confirmed delivery to {state_topic}")
            else:
                logger.warning(f"Message to {state_topic} may not have been delivered")

        except Exception as e:
            logger.error(f"Exception publishing to {state_topic}: {e}")

    def publish_availability(self, device_id, available=True):
        """Publish device availability."""
        avail_topic = f"thread/{device_id}/availability"
        payload = "online" if available else "offline"

        logger.info(f"Publishing availability: {device_id} = {payload}")

        result = self.client.publish(avail_topic, payload, qos=1, retain=True)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish availability: {result.rc}")

    def publish_sensor_availability(self, device_id, sensor_type, available=True):
        """Publish per-sensor availability for granular status in Home Assistant."""
        avail_topic = f"thread/{device_id}/{sensor_type}/availability"
        payload = "online" if available else "offline"

        logger.info(f"Publishing sensor availability: {device_id}/{sensor_type} = {payload}")

        result = self.client.publish(avail_topic, payload, qos=1, retain=True)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error(f"Failed to publish sensor availability: {result.rc}")

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
            "current": "A",
            "uptime": "s"
        }
        return units.get(resource_type.lower(), None)
