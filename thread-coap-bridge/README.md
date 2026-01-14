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

## Recent Changes (v0.1.0)

### Robustness Improvements

The bridge now handles device disconnection and reconnection gracefully:

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

New options in add-on configuration:

| Option | Default | Description |
|--------|---------|-------------|
| `offline_threshold_polls` | 5 | Failures before marking offline |
| `cleanup_after_hours` | 24 | Hours offline before removal |
| `cleanup_check_interval` | 3600 | Seconds between cleanup checks |

### Key Bug Fixes

1. **Device Re-discovery Bug** (Critical)
   - Fixed: Devices returning online were not being re-registered
   - Cause: `discovered_addresses` set was never cleared after device went offline
   - Solution: Added `forget_device()` method called when polling stops after max failures

2. **Database Schema Update**
   - Added `consecutive_failures` and `is_online` columns
   - Old databases are automatically deleted on first run with new schema

### How Device Recovery Works

1. **Device goes offline** (moved out of range, powered off)
2. **Polling fails** 5 times -> device marked "Unavailable" in HA
3. **Polling continues** for 30 more attempts, then stops
4. **Device removed** from `discovered_addresses` set
5. **Device returns** online (rejoins Thread network)
6. **Multicast discovery** finds device (within 60 seconds)
7. **Device re-registered** and polling resumes
8. **HA shows device** as online again

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
├── main.py              # Entry point, orchestration
├── config_handler.py    # Parse HA add-on configuration
├── coap_discovery.py    # Multicast discovery, parse /.well-known/core
├── coap_client.py       # CoAP GET/PUT/Observe operations
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
