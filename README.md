# Thread IoT Add-ons Repository

Home Assistant add-on repository for Thread/CoAP integration.

## Add-ons in this Repository

### Thread CoAP Bridge

Bridge CoAP devices on Thread networks to Home Assistant via MQTT Discovery.

**Features:**
- Automatic device discovery via CoAP multicast + unicast re-discovery
- Real-time state updates via CoAP polling
- MQTT Discovery integration (devices appear automatically in HA)
- Support for lights, switches, sensors, and battery monitoring
- Robust offline/online handling with automatic re-discovery

**Documentation:** See [thread-coap-bridge/DOCS.md](thread-coap-bridge/DOCS.md)

## Installation

1. In Home Assistant, go to **Settings** → **Add-ons** → **Add-on Store**
2. Click the menu (⋮) in the top right → **Repositories**
3. Add this repository URL: `https://github.com/Rosfly/thread-coap-bridge-addon`
4. Click **Add**
5. The add-on will appear in your add-on store

## Support

- **Issues:** https://github.com/Rosfly/thread-coap-bridge-addon/issues
- **Discussions:** https://github.com/Rosfly/thread-coap-bridge-addon/discussions

## Repository Structure

```
repository-root/
├── repository.yaml              # Repository metadata
└── thread-coap-bridge/          # Add-on directory
    ├── config.yaml              # Add-on configuration
    ├── Dockerfile               # Container build
    ├── DOCS.md                  # User documentation
    └── rootfs/                  # Container filesystem
        └── app/                 # Python application
```

## License

MIT License - See [thread-coap-bridge/LICENSE](thread-coap-bridge/LICENSE)
