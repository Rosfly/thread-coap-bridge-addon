"""Configuration handler for Home Assistant add-on."""
import os
import json
import logging

logger = logging.getLogger(__name__)


class ConfigHandler:
    """Handle Home Assistant add-on configuration."""
    
    def __init__(self):
        self.config = self._load_config()
        self._setup_logging()
    
    def _load_config(self):
        """Load configuration from Home Assistant Supervisor."""
        options_file = '/data/options.json'

        # Base config from options.json
        config = {}
        if os.path.exists(options_file):
            with open(options_file, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded from /data/options.json")
        else:
            # Fallback for development/testing
            logger.warning("Running in development mode - using defaults")
            config = {
                'discovery_interval': 60,
                'log_level': 'info',
                'thread_interface': 'wpan0',
                'multicast_address': 'ff03::fd'
            }

        # MQTT credentials come from environment variables (set by service script from Supervisor)
        # These override anything in options.json
        mqtt_host = os.getenv('MQTT_HOST')
        mqtt_port = os.getenv('MQTT_PORT')
        mqtt_user = os.getenv('MQTT_USER')
        mqtt_pass = os.getenv('MQTT_PASS')

        if mqtt_host:
            config['mqtt_host'] = mqtt_host
            logger.info(f"Using MQTT host from environment: {mqtt_host}")

        if mqtt_port:
            config['mqtt_port'] = int(mqtt_port)

        if mqtt_user:
            config['mqtt_user'] = mqtt_user
            logger.info(f"Using MQTT user from environment: {mqtt_user}")

        if mqtt_pass is not None:  # Allow empty password
            config['mqtt_password'] = mqtt_pass
            logger.info("Using MQTT password from environment")

        # Ensure all required fields exist
        config.setdefault('mqtt_host', 'core-mosquitto')
        config.setdefault('mqtt_port', 1883)
        config.setdefault('mqtt_user', '')
        config.setdefault('mqtt_password', '')

        return config
    
    def _setup_logging(self):
        """Configure logging based on user settings."""
        level_map = {
            'debug': logging.DEBUG,
            'info': logging.INFO,
            'warning': logging.WARNING,
            'error': logging.ERROR
        }
        
        level = level_map.get(
            self.config.get('log_level', 'info').lower(),
            logging.INFO
        )
        
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        
        logger.info(f"Logging level set to: {self.config.get('log_level', 'info')}")
    
    def get(self, key, default=None):
        """Get configuration value."""
        return self.config.get(key, default)
    
    @property
    def mqtt_config(self):
        """Return MQTT configuration dict."""
        return {
            'host': self.config['mqtt_host'],
            'port': self.config['mqtt_port'],
            'username': self.config['mqtt_user'],
            'password': self.config['mqtt_password']
        }
    
    @property
    def coap_config(self):
        """Return CoAP configuration dict."""
        return {
            'discovery_interval': self.config['discovery_interval'],
            'multicast_address': self.config['multicast_address'],
            'thread_interface': self.config.get('thread_interface', 'wpan0')
        }
