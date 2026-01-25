# Thread IoT Add-ons Repository

Home Assistant add-on repository for Thread/CoAP integration.

## Add-ons in this Repository

### Thread CoAP Bridge

Bridge CoAP devices on Thread networks to Home Assistant via MQTT Discovery.

**Features:**
- Automatic device discovery via CoAP multicast + unicast re-discovery
- Real-time state updates via CoAP Observe (LED/buttons) and polling (sensors)
- MQTT Discovery integration (devices appear automatically in HA)
- Support for lights, switches, sensors, and battery monitoring
- Per-sensor availability tracking for accurate status in Home Assistant
- Robust offline/online handling with automatic re-discovery
- Optimized for Sleepy End Devices (SED) with staggered polling

**Documentation:** See [thread-coap-bridge/DOCS.md](thread-coap-bridge/DOCS.md)

---

## Architecture

### Resource Handling Strategy

| Resource | Method | Interval | Features |
|----------|--------|----------|----------|
| LED | CoAP Observe | Real-time | Push notifications on state change |
| Button | CoAP Observe | Real-time | GPIO interrupt → immediate notify |
| Battery | Polling | 120s | Retry logic, per-sensor availability |
| Voltage | Polling | 120s | Retry logic, per-sensor availability |
| Uptime | Polling | 120s | Reboot detection → re-register observers |

### Staggered Polling for SED Efficiency

Sensors are polled with staggered delays to reduce burst load on the Thread parent router and ensure correct query order:

| Sensor | Initial Delay | Interval | Reason |
|--------|---------------|----------|--------|
| Battery | 0s | 120s | Queried first (voltage depends on fresh measurement) |
| Voltage | 40s | 120s | After battery completes |
| Uptime | 80s | 120s | Last, used for health monitoring |

### Reliability Features

| Feature | Description |
|---------|-------------|
| **Retry Logic** | On poll failure, immediate retry after 10s delay |
| **Per-Sensor Availability** | Each sensor has independent online/offline status |
| **Failure Threshold** | Sensor marked offline after 3 consecutive failures |
| **Auto-Recovery** | Sensor marked online on first successful poll |
| **Reboot Detection** | Uptime decrease triggers observer re-registration |

### MQTT Topics

```
thread/{device_id}/availability          # Device-level availability
thread/{device_id}/{sensor}/availability # Per-sensor availability
thread/{device_id}/{sensor}/state        # Sensor state value
homeassistant/{component}/{device_id}/{sensor}/config  # HA Discovery
```

### Sleepy End Device (SED) Support

- **65-second CoAP timeout**: Accommodates SED wake cycles (device polls parent every 15s)
- **120-second polling interval**: Reduces power consumption, aligned with slow-changing sensor values
- **Staggered requests**: Prevents request queue overflow at parent router

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
