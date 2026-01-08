# Thread CoAP Bridge

Automatically discover and integrate CoAP-enabled Thread devices into Home Assistant.

## What This Add-on Does

This add-on bridges CoAP devices on your Thread network to Home Assistant using MQTT Discovery. It:

- Automatically discovers Thread devices via CoAP multicast
- Monitors device state in real-time using CoAP Observe
- Creates Home Assistant entities automatically (lights, sensors, switches)
- Handles bidirectional control (HA → Device and Device → HA)

## Prerequisites

Before installing this add-on, you need:

1. **OpenThread Border Router (OTBR)** add-on installed and running
2. **Mosquitto broker** add-on installed and running  
3. At least one Thread device with CoAP server (e.g., nRF54L15 with Zephyr firmware)

## Installation

1. Navigate to **Settings** → **Add-ons** → **Add-on Store**
2. Click the menu (⋮) → **Repositories**
3. Add this repository URL: `https://github.com/yourusername/ha-addon-thread-coap-bridge`
4. Find "Thread CoAP Bridge" in the list
5. Click **Install**

## Configuration

### Basic Configuration

```yaml
mqtt_host: core-mosquitto
mqtt_port: 1883
mqtt_user: homeassistant
mqtt_password: your_secure_password
discovery_interval: 60
log_level: info
thread_interface: wpan0
multicast_address: ff03::fd
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `mqtt_host` | Hostname of MQTT broker | `core-mosquitto` |
| `mqtt_port` | MQTT broker port | `1883` |
| `mqtt_user` | MQTT username | `homeassistant` |
| `mqtt_password` | MQTT password | (empty) |
| `discovery_interval` | How often to scan for new devices (seconds) | `60` |
| `log_level` | Logging verbosity: debug, info, warning, error | `info` |
| `thread_interface` | Thread network interface name | `wpan0` |
| `multicast_address` | CoAP multicast address for discovery | `ff03::fd` |

## How It Works

1. **Discovery**: Periodically multicasts CoAP requests to find devices
2. **Resource Query**: Queries each device's `/.well-known/core` endpoint
3. **MQTT Publishing**: Creates Home Assistant entities via MQTT Discovery
4. **Observation**: Subscribes to device updates using CoAP Observe
5. **Control**: Translates HA commands to CoAP PUT requests

## Device Requirements

Your Thread/CoAP devices must implement:

- CoAP server listening on port 5683
- `/.well-known/core` endpoint for resource discovery
- Resources with CoRE Link Format attributes:
  - `rt` (resource type): e.g., "light", "sensor", "battery"
  - `if` (interface): e.g., "actuator", "sensor"  
  - `obs` flag for observable resources

Example resource advertisement:
```
</led>;rt="light";if="actuator";obs,
</switch>;rt="button";if="sensor";obs,
</battery>;rt="sensor";if="battery";obs
```

## Supported Device Types

The bridge automatically maps CoAP resources to Home Assistant entities:

| Resource Type | HA Entity Type | Features |
|--------------|----------------|----------|
| `light` / `led` | Light | On/Off control, real-time state |
| `switch` | Switch | On/Off control, real-time state |
| `button` | Binary Sensor | Button press detection |
| `battery` | Sensor | Battery percentage monitoring |
| `temperature` | Sensor | Temperature readings |
| `humidity` | Sensor | Humidity readings |

## Troubleshooting

### Devices Not Discovered

**Check Thread network is operational:**
```bash
ot-ctl state
# Should show: leader, router, or child
```

**Verify device has IPv6 address:**
```bash
ot-ctl ipaddr
```

**Test manual CoAP request:**
```bash
aiocoap-client -m GET coap://[device-ipv6]/.well-known/core
```

**Check add-on logs:**
- Click on the add-on
- Go to the **Log** tab
- Look for discovery attempts and errors

### MQTT Connection Failed

1. Ensure Mosquitto broker add-on is running
2. Verify credentials in add-on configuration
3. Check Mosquitto logs for authentication errors
4. Try connecting with MQTT Explorer to verify broker works

### Entities Not Appearing in Home Assistant

1. Verify MQTT Discovery is enabled:
   - **Settings** → **Devices & Services** → **MQTT**
   - Check "Enable discovery" is ON
2. Use MQTT Explorer to check topics under `homeassistant/`
3. Check Home Assistant logs for MQTT processing errors
4. Restart Home Assistant core

### Device Appears Offline

1. Check device is still joined to Thread network
2. Verify device is responding to ping: `ping6 [device-ipv6]`
3. Check if device went to sleep without proper keepalive
4. Look at bridge logs for connection errors

## Advanced Topics

### Custom Device Naming

Devices are automatically named using their EUI-64. To customize:

1. Wait for device to appear in HA
2. Go to **Settings** → **Devices & Services**
3. Find the device and click on it
4. Click the gear icon and rename

### Battery Life Optimization

For battery-powered devices:

- Configure as Sleepy End Device (SED) in firmware
- Set longer `discovery_interval` (e.g., 300 seconds)
- Use CoAP Observe for state updates instead of polling
- Implement proper sleep modes between transmissions

### Network Monitoring

Enable debug logging to see all CoAP traffic:

```yaml
log_level: debug
```

This shows:
- Multicast discovery attempts
- Device responses
- Resource queries
- Observe notifications
- MQTT publishing events

## Security Considerations

- **Thread Network**: All traffic is encrypted at the MAC layer with AES-128
- **MQTT**: Uses authentication (username/password)
- **CoAP**: Currently unencrypted application layer (DTLS support planned)

For enhanced security:
1. Use strong MQTT passwords
2. Keep Thread network key secure
3. Regularly update device firmware
4. Monitor logs for unusual activity

## Support & Issues

- **Documentation**: See README.md in repository
- **Issues**: https://github.com/yourusername/ha-addon-thread-coap-bridge/issues
- **Discussions**: https://github.com/yourusername/ha-addon-thread-coap-bridge/discussions

## License

MIT License - see LICENSE file in repository
