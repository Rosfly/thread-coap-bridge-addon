"""
CoAP Discovery Module

Handles multicast discovery of CoAP devices on Thread network
and parsing of /.well-known/core responses.
"""
import asyncio
import logging
import re
from aiocoap import Context, Message, GET, NON
from aiocoap.error import RequestTimedOut, Error

logger = logging.getLogger(__name__)


class CoAPDiscovery:
    """CoAP device discovery via multicast."""

    WELL_KNOWN_CORE = "/.well-known/core"
    DISCOVERY_TIMEOUT = 5.0  # seconds

    def __init__(self, device_registry, config):
        self.registry = device_registry
        self.multicast_address = config.get('multicast_address', 'ff03::fd')
        self.thread_interface = config.get('thread_interface', 'wpan0')
        self.context = None
        self.discovered_addresses = set()

        logger.info(f"CoAP Discovery initialized (multicast: {self.multicast_address})")

    async def initialize(self):
        """Initialize CoAP context."""
        try:
            self.context = await Context.create_client_context()
            logger.info("CoAP context initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CoAP context: {e}")
            raise

    async def discover_devices(self):
        """Perform multicast discovery."""
        logger.debug(f"Broadcasting discovery to {self.multicast_address}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return

        try:
            # Create multicast request to .well-known/core
            uri = f'coap://[{self.multicast_address}]{self.WELL_KNOWN_CORE}'
            request = Message(code=GET, uri=uri, mtype=NON)

            logger.debug(f"Sending multicast discovery to {uri}")

            # Multicast discovery: send and collect responses
            # We need to handle multiple responses from different devices
            responses = []
            request_handle = self.context.request(request)

            try:
                # Wait for initial response
                response = await asyncio.wait_for(
                    request_handle.response,
                    timeout=self.DISCOVERY_TIMEOUT
                )

                if response.payload:
                    source_addr = self._extract_source_address(response)
                    if source_addr and source_addr not in self.discovered_addresses:
                        logger.info(f"Discovered new device at {source_addr}")
                        self.discovered_addresses.add(source_addr)

                        # Parse resources and register device
                        resources = self._parse_core_link_format(response.payload.decode('utf-8'))
                        if resources:
                            await self.registry.register_device(source_addr, resources=resources)

            except asyncio.TimeoutError:
                logger.debug("Discovery timeout (normal for multicast)")
            except RequestTimedOut:
                logger.debug("CoAP request timed out (normal for multicast)")

        except Exception as e:
            logger.error(f"Discovery error: {e}", exc_info=True)

    async def query_device_resources(self, ipv6_addr):
        """Query individual device for its resources."""
        logger.debug(f"Querying resources from {ipv6_addr}")

        if not self.context:
            logger.error("CoAP context not initialized")
            return []

        try:
            # Unicast request to specific device
            uri = f'coap://[{ipv6_addr}]{self.WELL_KNOWN_CORE}'
            request = Message(code=GET, uri=uri)

            response = await asyncio.wait_for(
                self.context.request(request).response,
                timeout=5.0
            )

            if response.payload:
                payload = response.payload.decode('utf-8')
                logger.info(f"Received resources from {ipv6_addr}: {payload}")
                return self._parse_core_link_format(payload)
            else:
                logger.warning(f"Empty response from {ipv6_addr}")
                return []

        except asyncio.TimeoutError:
            logger.warning(f"Query timeout for device {ipv6_addr}")
            return []
        except Exception as e:
            logger.error(f"Error querying device {ipv6_addr}: {e}")
            return []

    def _parse_core_link_format(self, payload):
        """
        Parse CoRE Link Format (RFC 6690).

        Example: </led>;rt="led";if="actuator",</sw>;rt="button";if="sensor"
        """
        resources = []

        try:
            # Pattern to match: </uri>;rt="type";if="interface"
            # Also handle optional obs attribute
            pattern = r'<([^>]+)>(?:;rt="([^"]+)")?(?:;if="([^"]+)")?(?:;obs)?'

            matches = re.findall(pattern, payload)

            for uri_path, rt, iface in matches:
                resource = {
                    'uri_path': uri_path,
                    'resource_type': rt if rt else 'unknown',
                    'interface_type': iface if iface else None,
                    'observable': ';obs' in payload  # Simple check for observable
                }
                resources.append(resource)
                logger.debug(f"Parsed resource: {resource}")

            logger.info(f"Parsed {len(resources)} resources from CoRE Link Format")

        except Exception as e:
            logger.error(f"Error parsing CoRE Link Format: {e}")

        return resources

    def _extract_source_address(self, response):
        """Extract source IPv6 address from CoAP response."""
        try:
            # aiocoap stores remote address in response.remote
            if hasattr(response, 'remote') and response.remote:
                # remote is typically a tuple (host, port)
                if isinstance(response.remote, tuple):
                    return response.remote[0]
                return str(response.remote)
            return None
        except Exception as e:
            logger.error(f"Error extracting source address: {e}")
            return None

    async def start_periodic_discovery(self, interval):
        """Run discovery loop."""
        logger.info(f"Starting periodic discovery (interval: {interval}s)")

        while True:
            try:
                await self.discover_devices()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Discovery loop error: {e}")
                await asyncio.sleep(interval)

    async def shutdown(self):
        """Cleanup and close CoAP context."""
        if self.context:
            await self.context.shutdown()
            logger.info("CoAP discovery context shut down")
