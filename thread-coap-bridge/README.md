# Thread CoAP Bridge - Home Assistant Add-on 2.0

A Home Assistant add-on that bridges CoAP-enabled devices on Thread networks to Home Assistant via MQTT Discovery.

## Features

- Automatic device discovery via CoAP multicast
- Real-time state updates using CoAP polling
- MQTT Discovery integration (devices appear automatically in HA)
- Support for lights, switches, sensors, and battery monitoring
- Multi-architecture support (amd64, aarch64, armv7)
- **Robust offline detection** with configurable thresholds
- **Automatic device cleanup** for long-offline devices
- **Automatic re-discovery** when devices return online
- **SED (Sleepy End Device) support** with 65-second timeouts

## Recent Changes (v0.4.0)

### SED (Sleepy End Device) Support

Added full support for Thread Sleepy End Devices, which sleep most of the time to conserve battery.

#### How SED Devices Work

SED devices keep their radio OFF between poll intervals (typically 60 seconds) to achieve ultra-low power consumption. When the bridge sends a request to an SED:

1. Request is sent to the SED's IPv6 address
2. Parent router queues the request (SED is sleeping)
3. SED wakes at its next poll interval (up to 60s later)
4. SED receives the queued request from parent
5. SED processes and responds
6. Bridge receives response

#### Changes for SED Support

**Increased timeouts to 65 seconds** (longer than typical 60s poll period):

| Function | Old Timeout | New Timeout |
|----------|-------------|-------------|
| `get_resource()` | 10s | 65s |
| `put_resource()` | 10s | 65s |
| `observe_resource()` initial | 15s | 65s |
| `query_device_resources()` | 5s | 65s |

**Why 65 seconds?** SED devices poll every 60 seconds by default. The extra 5 seconds provides margin for network latency and processing time.

#### SED Device Discovery

SED devices require special handling for initial discovery:

1. **During boot**: SED firmware stays awake for a "grace period" (typically 2 minutes)
2. **Bridge discovers device** via multicast during this window
3. **After grace period**: Device enters SED sleep mode
4. **Re-discovery**: Uses unicast probing to last-known IPv6 (works with SED)

#### Latency Expectations with SED

| Operation | MTD (always-on) | SED (sleepy) |
|-----------|-----------------|--------------|
| Button notification | ~50ms | ~100-200ms |
| GET /battery | ~50ms | Up to 60s |
| PUT /led | ~50ms | Up to 60s |

**Note:** Button notifications remain fast because the SED wakes immediately on GPIO interrupt and sends the notification. Only *incoming* requests have latency.

---

## Recent Changes (v0.3.0)

### Unicast Re-Discovery Fix

Fixed critical issue where devices could not be re-discovered after extended disconnection (~15+ minutes).

#### Problem
After a device went offline for extended period and returned, multicast discovery failed to find it. The device stayed "Unavailable" in Home Assistant indefinitely.

#### Root Cause
The aiocoap library has a known limitation with multicast on Thread/wpan0 interfaces - it falls back to broken unicast behavior with the warning: `"Sending request to multicast via unicast request method"`. This means multicast discovery was never truly reliable.

#### Solution
Added **unicast re-discovery** that probes known offline devices directly:

1. When a device is marked offline (5 failures), its IP is removed from the discovery cache
2. Every discovery cycle (60s), the bridge queries offline devices via **unicast CoAP GET** to their last-known IPv6
3. Since SLAAC addresses (based on EUI-64) are stable across Thread reconnections, this reliably finds returning devices
4. Device is re-registered and polling resumes automatically

#### New Files/Methods
- `device_registry.py`: Added `get_offline_devices()` - queries devices where `is_online=0`
- `coap_discovery.py`: Added `rediscover_offline_devices()` - probes offline devices via unicast
- `main.py`: Discovery loop now calls both multicast and unicast re-discovery
- `coap_client.py`: Calls `forget_device()` when marking offline (not just at max_failures)

---

## Recent Changes (v0.2.0)

### LED State Display Fix

Fixed critical issue where LED state was not being displayed correctly in Home Assistant UI.

#### Problem
The LED would show "unknown" or wrong state in HA even though the device was responding correctly.

#### Root Causes & Solutions

1. **MQTT Discovery Schema Mismatch**
   - Problem: Discovery used `"schema": "json"` which expects `{"state": "ON"}`, but bridge published `"1"` or `"0"`
   - Solution: Switched to basic light schema with `state_value_template`:
     ```python
     payload["state_value_template"] = "{{ 'ON' if value == '1' else 'OFF' }}"
     ```

2. **Device Response Format**
   - Problem: Expected `{"state": 1}` but device returns `{"leds": [{"led_id": 0, "state": 1}]}`
   - Solution: Updated `publish_state()` to extract state from nested array:
     ```python
     if 'leds' in state_value and len(state_value['leds']) > 0:
         led_state = state_value['leds'][0].get('state', 0)
         payload = str(led_state)
     ```

3. **UI Flickering After Commands**
   - Problem: User toggles LED -> UI shows new state -> poll returns old state -> UI flickers back
   - Solution: Implemented optimistic updates with suppression window:
     - Immediately publish expected state when command is sent
     - Suppress poll updates for 10 seconds after command
     - Clear suppression when device confirms expected state or timeout expires

#### MQTT State Publishing

States are now published with `retain=True` so Home Assistant remembers state across restarts:
```python
self.client.publish(state_topic, payload, qos=1, retain=True)
```

### Robustness Improvements (v0.1.0)

The bridge handles device disconnection and reconnection gracefully:

#### Offline Detection
- Tracks consecutive poll failures per device
- Marks device as **offline** in Home Assistant after 5 consecutive failures (~1 minute)
- Publishes MQTT availability="offline" so HA shows "Unavailable"

#### Polling Behavior
- Stops polling after 35 consecutive failures (5 offline threshold + 30 extra)
- Removes device from discovery cache to allow re-registration
- Discovery continues to run and will find the device when it returns

#### Device Cleanup
- Background task runs hourly to clean up stale devices
- Removes devices offline for >24 hours (configurable)
- Publishes empty MQTT discovery configs to remove from HA UI

#### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `offline_threshold_polls` | 5 | Failures before marking offline |
| `cleanup_after_hours` | 24 | Hours offline before removal |
| `cleanup_check_interval` | 3600 | Seconds between cleanup checks |

#### SED vs MTD Devices

The bridge automatically handles both device types:

| Feature | MTD (Mobile Thread Device) | SED (Sleepy End Device) |
|---------|---------------------------|------------------------|
| Radio | Always listening | Sleeps between polls |
| Power consumption | Higher (~mA) | Ultra-low (~µA) |
| Request latency | Immediate (~50ms) | Up to poll period (60s) |
| Push notifications | Immediate | Immediate (GPIO wakes device) |
| Discovery | Multicast works | Requires grace period at boot |

**Identifying device type** on the border router:
```shell
ot-ctl neighbor table
# R=0 → SED (RxOnWhenIdle=false)
# R=1 → MTD (RxOnWhenIdle=true)
```

### Key Bug Fixes

1. **Device Re-discovery Bug** (Critical)
   - Fixed: Devices returning online were not being re-registered
   - Cause: `discovered_addresses` set was never cleared after device went offline
   - Solution: Added `forget_device()` method called when polling stops after max failures

2. **LED State Not Showing** (Critical)
   - Fixed: LED state showing "unknown" in HA UI
   - Cause: Multiple issues - wrong MQTT schema, wrong JSON format parsing, no state retention
   - Solution: Comprehensive fix to MQTT discovery, state extraction, and retention

3. **Command Translation**
   - Fixed: Commands from HA not being translated correctly to device format
   - Cause: HA sends "ON"/"OFF" strings, device expects `{"led_id": 0, "state": 1}`
   - Solution: `_translate_mqtt_to_coap()` now handles both JSON and plain text formats

4. **Database Schema Update**
   - Added `consecutive_failures` and `is_online` columns
   - Old databases are automatically deleted on first run with new schema

### How Device Recovery Works

1. **Device goes offline** (moved out of range, powered off)
2. **Polling fails** 5 times -> device marked "Unavailable" in HA
3. **Device removed** from `discovered_addresses` set immediately (allows re-discovery)
4. **Polling continues** for 30 more attempts, then stops
5. **Device returns** online (rejoins Thread network)
6. **Unicast re-discovery** probes last-known IPv6 (every 60 seconds)
7. **Device responds** to unicast GET `/.well-known/core`
8. **Device re-registered** and polling resumes
9. **HA shows device** as online again

**Note:** Multicast discovery is unreliable on Thread/wpan0 due to aiocoap limitations. The unicast re-discovery mechanism ensures devices are found reliably after extended disconnection.

## Lessons Learned

### MQTT Discovery for Lights

Home Assistant MQTT lights support multiple schemas. For simple ON/OFF lights:
- **Don't use JSON schema** unless you want to publish `{"state": "ON"}`
- Use **basic schema** with `state_value_template` to convert device values
- Always set `retain=True` for state topics

### Device Response Formats

CoAP devices may return complex nested JSON. Always log the actual response format:
```python
logger.info(f"publish_state called: device={device_id}, uri={resource_uri}, value={state_value}")
```

### Optimistic Updates

For responsive UI, publish the expected state immediately when a command is sent, then verify with the next poll. This prevents the "springback" effect where the UI briefly shows the old state.

### State Extraction

Handle multiple response formats for robustness:
```python
# Format 1: {"leds": [{"led_id": 0, "state": 1}]}
# Format 2: {"state": 1}
# Format 3: "1"
```

## Development

### Local Testing

```bash
# Clone the repository
git clone https://github.com/yourusername/ha-addon-thread-coap-bridge.git
cd ha-addon-thread-coap-bridge

# Build locally
docker build -t thread-coap-bridge .

# Run for testing (requires OTBR and Mosquitto running)
docker run --rm \
  --network host \
  --privileged \
  -v $(pwd)/test-data:/data \
  thread-coap-bridge
```

### Testing Python Code Directly

```bash
cd rootfs/app

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r ../../requirements.txt

# Create test configuration
mkdir -p /tmp/addon-data
cat > /tmp/addon-data/options.json << EOF
{
  "mqtt_host": "localhost",
  "mqtt_port": 1883,
  "mqtt_user": "test",
  "mqtt_password": "test",
  "discovery_interval": 60,
  "log_level": "debug",
  "thread_interface": "wpan0",
  "multicast_address": "ff03::fd"
}
EOF

# Run the service
python3 main.py
```

### Installing in Home Assistant

#### Method 1: Local Development

1. SSH into Home Assistant host
2. Create directory: `mkdir -p /addons/thread-coap-bridge`
3. Copy files to this directory
4. In HA: Settings → Add-ons → Add-on Store → ⋮ → Repositories
5. Add local path: `/addons`
6. Install from Local Add-ons section

#### Method 2: GitHub Repository

1. Push code to GitHub
2. In HA: Settings → Add-ons → Add-on Store → ⋮ → Repositories  
3. Add: `https://github.com/yourusername/ha-addon-thread-coap-bridge`
4. Install from repository

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Home Assistant Container                             │
│  ├── Core (Python)                                   │
│  ├── Supervisor                                      │
│  │   ├── OTBR Add-on (Thread Border Router)         │
│  │   ├── Mosquitto Add-on (MQTT Broker)             │
│  │   └── CoAP Bridge Add-on (This)                  │
│  │       ├── CoAP Discovery (multicast ff03::fd)    │
│  │       ├── CoAP Client (Observe)                  │
│  │       ├── Device Registry (SQLite)               │
│  │       └── MQTT Publisher (Discovery)             │
└─────────────────────────────────────────────────────┘
                      ▲
                      │ Thread Mesh (802.15.4)
                      │
        ┌─────────────┼─────────────┐
        │             │             │
   ┌────▼───┐   ┌────▼───┐   ┌────▼───┐
   │ nRF54L15│   │ nRF54L15│   │ nRF54L15│
   │ CoAP    │   │ CoAP    │   │ CoAP    │
   │ Server  │   │ Server  │   │ Server  │
   └─────────┘   └─────────┘   └─────────┘
```

## Code Structure

```
rootfs/app/
├── main.py              # Entry point, orchestration, discovery loop
├── config_handler.py    # Parse HA add-on configuration
├── coap_discovery.py    # Multicast + unicast discovery, parse /.well-known/core
├── coap_client.py       # CoAP GET/PUT/Observe operations, failure tracking
├── mqtt_publisher.py    # MQTT Discovery, state publishing
├── device_registry.py   # SQLite database for device management
└── models.py            # Data models (Device, Resource)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## License

MIT License - see LICENSE file

## Credits

Built with:
- [aiocoap](https://github.com/chrysn/aiocoap) - Python CoAP library
- [paho-mqtt](https://www.eclipse.org/paho/) - MQTT client library
- [OpenThread](https://openthread.io/) - Thread networking stack
- [Home Assistant](https://www.home-assistant.io/) - Home automation platform
