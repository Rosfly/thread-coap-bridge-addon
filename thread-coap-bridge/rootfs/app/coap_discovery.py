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
    MULTICAST_GROUPS = ['ff03::fd', 'ff03::1']  # Try both CoAP nodes and all Thread nodes

    def __init__(self, device_registry, config):
        self.registry = device_registry
        self.multicast_address = config.get('multicast_address', 'ff03::fd')  # Kept for backwards compat
        self.thread_interface = config.get('thread_interface', 'wpan0')
        self.context = None
        self.discovered_addresses = set()

        logger.info(f"CoAP Discovery initialized (trying groups: {', '.join(self.MULTICAST_GROUPS)})")

    async def initialize(self):
        """Initialize CoAP context."""
        try:
            self.context = await Context.create_client_context()
            logger.info("CoAP context initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize CoAP context: {e}")
            raise

    async def discover_devices(self):
        """Perform multicast discovery to all Thread multicast groups."""
        if not self.context:
            logger.error("CoAP context not initialized")
            return

        # Try both ff03::fd (CoAP nodes) and ff03::1 (all Thread nodes)
        for mcast_addr in self.MULTICAST_GROUPS:
            try:
                # Send with interface scope to ensure packets go to wpan0
                uri = f'coap://[{mcast_addr}%{self.thread_interface}]{self.WELL_KNOWN_CORE}'
                logger.info(f"Sending multicast discovery to {uri}")

                request = Message(code=GET, uri=uri, mtype=NON)

                # Send and wait for responses
                pr = self.context.request(request)

                try:
                    # Wait for first response (multicast typically gets one per device)
                    response = await asyncio.wait_for(
                        pr.response,
                        timeout=self.DISCOVERY_TIMEOUT
                    )

                    if response and response.payload:
                        source_addr = self._extract_source_address(response)
                        if source_addr and source_addr not in self.discovered_addresses:
                            logger.info(f"✓ Discovered device at {source_addr} via {mcast_addr}")
                            self.discovered_addresses.add(source_addr)

                            # Parse and register
                            resources = self._parse_core_link_format(response.payload.decode('utf-8'))
                            if resources:
                                await self.registry.register_device(source_addr, resources=resources)

                except asyncio.TimeoutError:
                    logger.debug(f"No response from {mcast_addr} (timeout)")

            except Exception as e:
                logger.error(f"Error with multicast {mcast_addr}: {e}")

        if not self.discovered_addresses:
            logger.warning("No devices discovered via multicast - devices may not be responding to multicast")

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
                # remote can be a tuple (host, port) or UDP6EndpointAddress object
                if isinstance(response.remote, tuple):
                    addr = response.remote[0]
                else:
                    # It's an aiocoap UDP6EndpointAddress object
                    addr = str(response.remote)

                # Extract just the IPv6 address from various formats:
                # - "fd70:c012:66ce:1:dd63:96f1:60f6:a43f"
                # - "[fd70:c012:66ce:1:dd63:96f1:60f6:a43f]"
                # - "<UDP6EndpointAddress [fd70:...] (locally ...)>"

                # If it contains '<UDP6EndpointAddress', extract the bracketed address
                if '<UDP6EndpointAddress' in addr:
                    import re
                    match = re.search(r'\[([0-9a-f:]+)\]', addr)
                    if match:
                        addr = match.group(1)

                # Remove brackets if present
                addr = addr.strip('[]')

                # Remove interface suffix if present (e.g., %wpan0)
                addr = addr.split('%')[0]

                logger.debug(f"Extracted address: {addr}")
                return addr
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
