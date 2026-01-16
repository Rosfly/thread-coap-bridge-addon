"""
Device Registry Module

SQLite database for managing discovered devices and their resources.
"""
import logging
import sqlite3
import aiosqlite
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)


class DeviceRegistry:
    """Device registry with SQLite backend."""

    def __init__(self, db_path='/data/devices.db'):
        self.db_path = db_path
        self.connection = None

        logger.info(f"Device Registry initialized (database: {db_path})")

    async def initialize(self):
        """Initialize SQLite database and create tables."""
        try:
            self.connection = await aiosqlite.connect(self.db_path)
            await self._create_tables()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _create_tables(self):
        """Create database schema."""
        try:
            async with self.connection.cursor() as cursor:
                # Devices table
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS devices (
                        device_id TEXT PRIMARY KEY,
                        ipv6_address TEXT NOT NULL,
                        eui64 TEXT,
                        last_seen TIMESTAMP,
                        commissioned INTEGER DEFAULT 0,
                        consecutive_failures INTEGER DEFAULT 0,
                        is_online INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Resources table
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS resources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id TEXT NOT NULL,
                        uri_path TEXT NOT NULL,
                        resource_type TEXT,
                        interface_type TEXT,
                        observable INTEGER DEFAULT 0,
                        FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
                        UNIQUE(device_id, uri_path)
                    )
                ''')

                # Create indexes
                await cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_devices_commissioned
                    ON devices(commissioned)
                ''')

                await cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_resources_device
                    ON resources(device_id)
                ''')

                await self.connection.commit()
                logger.debug("Database tables created successfully")

        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise

    async def register_device(self, ipv6_address, eui64=None, resources=None):
        """Register a new device."""
        device_id = self._generate_device_id(ipv6_address, eui64)

        logger.info(f"Registering device: {device_id} ({ipv6_address})")

        try:
            async with self.connection.cursor() as cursor:
                # Insert or update device
                # Reset commissioned to 0 on re-discovery to trigger re-commissioning
                # Also reset failure counters and mark as online
                await cursor.execute('''
                    INSERT INTO devices (device_id, ipv6_address, eui64, last_seen, commissioned,
                                        consecutive_failures, is_online)
                    VALUES (?, ?, ?, ?, 0, 0, 1)
                    ON CONFLICT(device_id) DO UPDATE SET
                        ipv6_address=excluded.ipv6_address,
                        last_seen=excluded.last_seen,
                        commissioned=0,
                        consecutive_failures=0,
                        is_online=1
                ''', (device_id, ipv6_address, eui64, datetime.now()))

                # Insert resources if provided
                if resources:
                    for resource in resources:
                        await cursor.execute('''
                            INSERT OR REPLACE INTO resources
                            (device_id, uri_path, resource_type, interface_type, observable)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (
                            device_id,
                            resource['uri_path'],
                            resource.get('resource_type', 'unknown'),
                            resource.get('interface_type'),
                            1 if resource.get('observable', False) else 0
                        ))

                await self.connection.commit()
                logger.info(f"Device {device_id} registered with {len(resources) if resources else 0} resources")

        except Exception as e:
            logger.error(f"Error registering device {device_id}: {e}")
            raise

        return device_id

    async def get_uncommissioned_devices(self):
        """Get devices that haven't been commissioned yet."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    SELECT device_id, ipv6_address, eui64, last_seen, commissioned
                    FROM devices
                    WHERE commissioned = 0
                ''')

                rows = await cursor.fetchall()

                devices = []
                for row in rows:
                    device = Device(
                        device_id=row[0],
                        ipv6_address=row[1],
                        eui64=row[2],
                        last_seen=datetime.fromisoformat(row[3]) if row[3] else None,
                        commissioned=bool(row[4])
                    )
                    devices.append(device)

                logger.debug(f"Found {len(devices)} uncommissioned devices")
                return devices

        except Exception as e:
            logger.error(f"Error getting uncommissioned devices: {e}")
            return []

    async def get_device_by_id(self, device_id):
        """Get device by ID."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    SELECT device_id, ipv6_address, eui64, last_seen, commissioned
                    FROM devices
                    WHERE device_id = ?
                ''', (device_id,))

                row = await cursor.fetchone()

                if row:
                    return Device(
                        device_id=row[0],
                        ipv6_address=row[1],
                        eui64=row[2],
                        last_seen=datetime.fromisoformat(row[3]) if row[3] else None,
                        commissioned=bool(row[4])
                    )
                return None

        except Exception as e:
            logger.error(f"Error getting device {device_id}: {e}")
            return None

    async def get_device_resources(self, device_id):
        """Get all resources for a device."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    SELECT uri_path, resource_type, interface_type, observable
                    FROM resources
                    WHERE device_id = ?
                ''', (device_id,))

                rows = await cursor.fetchall()

                resources = []
                for row in rows:
                    resource = Resource(
                        uri_path=row[0],
                        resource_type=row[1],
                        interface_type=row[2],
                        observable=bool(row[3])
                    )
                    resources.append(resource)

                logger.debug(f"Found {len(resources)} resources for device {device_id}")
                return resources

        except Exception as e:
            logger.error(f"Error getting resources for device {device_id}: {e}")
            return []

    async def mark_commissioned(self, device_id):
        """Mark device as commissioned."""
        logger.info(f"Marking device as commissioned: {device_id}")

        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    UPDATE devices
                    SET commissioned = 1
                    WHERE device_id = ?
                ''', (device_id,))

                await self.connection.commit()

        except Exception as e:
            logger.error(f"Error marking device commissioned: {e}")

    async def update_last_seen(self, device_id):
        """Update device's last_seen timestamp."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    UPDATE devices
                    SET last_seen = ?
                    WHERE device_id = ?
                ''', (datetime.now(), device_id))

                await self.connection.commit()

        except Exception as e:
            logger.error(f"Error updating last_seen for {device_id}: {e}")

    async def decommission_device(self, device_id):
        """Remove device from registry."""
        logger.info(f"Decommissioning device: {device_id}")

        try:
            async with self.connection.cursor() as cursor:
                # Delete device (resources will be deleted automatically due to CASCADE)
                await cursor.execute('''
                    DELETE FROM devices
                    WHERE device_id = ?
                ''', (device_id,))

                await self.connection.commit()

        except Exception as e:
            logger.error(f"Error decommissioning device {device_id}: {e}")

    async def update_device_failure(self, device_id, failed=True):
        """
        Update device failure counter.

        Args:
            device_id: Device identifier
            failed: True if poll failed, False if successful
        """
        try:
            async with self.connection.cursor() as cursor:
                if failed:
                    # Increment failure counter
                    await cursor.execute('''
                        UPDATE devices
                        SET consecutive_failures = consecutive_failures + 1
                        WHERE device_id = ?
                    ''', (device_id,))
                else:
                    # Reset failure counter and update last_seen
                    await cursor.execute('''
                        UPDATE devices
                        SET consecutive_failures = 0,
                            last_seen = ?,
                            is_online = 1
                        WHERE device_id = ?
                    ''', (datetime.now(), device_id))

                await self.connection.commit()

        except Exception as e:
            logger.error(f"Error updating device failure state for {device_id}: {e}")

    async def mark_device_offline(self, device_id):
        """Mark device as offline in database."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    UPDATE devices
                    SET is_online = 0
                    WHERE device_id = ?
                ''', (device_id,))

                await self.connection.commit()
                logger.info(f"Device {device_id} marked as offline in database")

        except Exception as e:
            logger.error(f"Error marking device offline: {e}")

    async def get_offline_devices(self):
        """
        Get devices that are offline but still in database (not yet cleaned up).
        These are candidates for unicast re-discovery.
        """
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    SELECT device_id, ipv6_address, eui64, last_seen, commissioned
                    FROM devices
                    WHERE is_online = 0 AND commissioned = 1
                ''')

                rows = await cursor.fetchall()

                devices = []
                for row in rows:
                    device = Device(
                        device_id=row[0],
                        ipv6_address=row[1],
                        eui64=row[2],
                        last_seen=datetime.fromisoformat(row[3]) if row[3] else None,
                        commissioned=bool(row[4])
                    )
                    devices.append(device)

                return devices

        except Exception as e:
            logger.error(f"Error getting offline devices: {e}")
            return []

    async def get_devices_for_cleanup(self, offline_hours=24):
        """
        Get devices that have been offline for more than specified hours.

        Args:
            offline_hours: Hours threshold for cleanup

        Returns:
            List of Device objects to be cleaned up
        """
        try:
            async with self.connection.cursor() as cursor:
                cutoff_time = datetime.now() - timedelta(hours=offline_hours)

                await cursor.execute('''
                    SELECT device_id, ipv6_address, eui64, last_seen, commissioned
                    FROM devices
                    WHERE is_online = 0
                      AND last_seen < ?
                      AND commissioned = 1
                ''', (cutoff_time,))

                rows = await cursor.fetchall()

                devices = []
                for row in rows:
                    device = Device(
                        device_id=row[0],
                        ipv6_address=row[1],
                        eui64=row[2],
                        last_seen=datetime.fromisoformat(row[3]) if row[3] else None,
                        commissioned=bool(row[4])
                    )
                    devices.append(device)

                logger.debug(f"Found {len(devices)} devices eligible for cleanup")
                return devices

        except Exception as e:
            logger.error(f"Error getting devices for cleanup: {e}")
            return []

    async def get_device_failure_count(self, device_id):
        """Get consecutive failure count for a device."""
        try:
            async with self.connection.cursor() as cursor:
                await cursor.execute('''
                    SELECT consecutive_failures
                    FROM devices
                    WHERE device_id = ?
                ''', (device_id,))

                row = await cursor.fetchone()
                return row[0] if row else 0

        except Exception as e:
            logger.error(f"Error getting failure count for {device_id}: {e}")
            return 0

    async def close(self):
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            logger.info("Database connection closed")

    def _generate_device_id(self, ipv6_address, eui64=None):
        """Generate unique device ID."""
        if eui64:
            return f"thread_{eui64.replace(':', '')}"
        else:
            # Use last 4 segments of IPv6 address
            parts = ipv6_address.split(':')
            suffix = ''.join(parts[-4:]) if len(parts) >= 4 else ipv6_address.replace(':', '')
            return f"thread_{suffix}"


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
