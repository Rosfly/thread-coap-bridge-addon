"""
Device Registry Module

SQLite database for managing discovered devices and their resources.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Device registry with SQLite backend."""
    
    def __init__(self, db_path='/data/devices.db'):
        self.db_path = db_path
        self.connection = None
        
        logger.info(f"Device Registry initialized (database: {db_path})")
        
        # TODO: Initialize SQLite database
        # TODO: Create tables if they don't exist
    
    def _create_tables(self):
        """Create database schema."""
        # TODO: Create devices table
        # TODO: Create resources table
        pass
    
    async def register_device(self, ipv6_address, eui64=None, resources=None):
        """Register a new device."""
        device_id = self._generate_device_id(ipv6_address, eui64)
        
        logger.info(f"Registering device: {device_id} ({ipv6_address})")
        
        # TODO: Insert device into database
        # TODO: Insert resources
        # TODO: Set commissioned=False
        
        return device_id
    
    async def get_uncommissioned_devices(self):
        """Get devices that haven't been commissioned yet."""
        # TODO: Query database for devices with commissioned=False
        # TODO: Return list of device objects
        
        return []
    
    async def get_device_resources(self, device_id):
        """Get all resources for a device."""
        # TODO: Query database for resources
        # TODO: Return list of resource objects
        
        return []
    
    async def mark_commissioned(self, device_id):
        """Mark device as commissioned."""
        logger.info(f"Marking device as commissioned: {device_id}")
        
        # TODO: Update database: SET commissioned=True
        
        pass
    
    async def update_last_seen(self, device_id):
        """Update device's last_seen timestamp."""
        # TODO: Update database with current timestamp
        pass
    
    async def decommission_device(self, device_id):
        """Remove device from registry."""
        logger.info(f"Decommissioning device: {device_id}")
        
        # TODO: Delete from database
        
        pass
    
    def _generate_device_id(self, ipv6_address, eui64=None):
        """Generate unique device ID."""
        if eui64:
            return f"thread_{eui64.replace(':', '')}"
        else:
            # Use last part of IPv6 address
            return f"thread_{ipv6_address.split(':')[-1]}"


class Device:
    """Device model."""
    
    def __init__(self, device_id, ipv6_address, eui64=None, 
                 last_seen=None, commissioned=False):
        self.device_id = device_id
        self.ipv6_address = ipv6_address
        self.eui64 = eui64
        self.last_seen = last_seen or datetime.now()
        self.commissioned = commissioned


class Resource:
    """Resource model."""
    
    def __init__(self, uri_path, resource_type, interface_type=None, 
                 observable=False):
        self.uri_path = uri_path
        self.resource_type = resource_type
        self.interface_type = interface_type
        self.observable = observable
