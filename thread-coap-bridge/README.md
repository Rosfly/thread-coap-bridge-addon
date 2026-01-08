# Thread CoAP Bridge - Home Assistant Add-on 2.0

A Home Assistant add-on that bridges CoAP-enabled devices on Thread networks to Home Assistant via MQTT Discovery.

## Features

- Automatic device discovery via CoAP multicast
- Real-time state updates using CoAP Observe
- MQTT Discovery integration (devices appear automatically in HA)
- Support for lights, switches, sensors, and battery monitoring
- Multi-architecture support (amd64, aarch64, armv7)

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
