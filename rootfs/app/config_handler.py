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
        
        # In HA add-ons, config is passed via /data/options.json
        if os.path.exists(options_file):
            with open(options_file, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded from /data/options.json")
                return config
        else:
            # Fallback for development/testing
            logger.warning("Running in development mode - using environment variables")
            return {
                'mqtt_host': os.getenv('MQTT_HOST', 'localhost'),
                'mqtt_port': int(os.getenv('MQTT_PORT', '1883')),
                'mqtt_user': os.getenv('MQTT_USER', 'homeassistant'),
                'mqtt_password': os.getenv('MQTT_PASS', ''),
                'discovery_interval': int(os.getenv('DISCOVERY_INTERVAL', '60')),
                'log_level': os.getenv('LOG_LEVEL', 'info'),
                'thread_interface': os.getenv('THREAD_INTERFACE', 'wpan0'),
                'multicast_address': os.getenv('MULTICAST_ADDRESS', 'ff03::fd')
            }
    
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
