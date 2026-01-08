# Installation Guide

## Quick Start

### Prerequisites

1. **Home Assistant** (HA OS, Supervised, or Container)
2. **OpenThread Border Router** add-on installed and running
3. **Mosquitto broker** add-on installed and running
4. At least one Thread device with CoAP server

### Installation Steps

#### Option 1: Local Installation (Development/Testing)

1. **SSH into Home Assistant:**
   ```bash
   ssh root@homeassistant.local
   # Or use the Terminal & SSH add-on
   ```

2. **Create add-on directory:**
   ```bash
   mkdir -p /addons/thread-coap-bridge
   cd /addons/thread-coap-bridge
   ```

3. **Copy add-on files:**
   ```bash
   # Extract the downloaded zip file to this directory
   # Or use git if available:
   # git clone https://github.com/yourusername/ha-addon-thread-coap-bridge.git .
   ```

4. **Tell Home Assistant about local add-ons:**
   - Open Home Assistant web interface
   - Go to **Settings** → **Add-ons** → **Add-on Store**
   - Click the menu icon (⋮) in the top right
   - Select **Repositories**
   - Add local path: `/addons`
   - Click **Add**

5. **Install the add-on:**
   - Refresh the add-on store page
   - Look for "Thread CoAP Bridge" under **Local Add-ons**
   - Click on it
   - Click **Install**

#### Option 2: GitHub Repository (Recommended)

1. **Push code to GitHub:**
   ```bash
   # On your development machine
   cd thread-coap-bridge-addon
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/yourusername/ha-addon-thread-coap-bridge.git
   git push -u origin main
   ```

2. **Add repository to Home Assistant:**
   - Open Home Assistant
   - Go to **Settings** → **Add-ons** → **Add-on Store**
   - Click menu (⋮) → **Repositories**
   - Add: `https://github.com/yourusername/ha-addon-thread-coap-bridge`
   - Click **Add**

3. **Install the add-on:**
   - Refresh the add-on store
   - Find "Thread CoAP Bridge"
   - Click **Install**

### Configuration

1. **Click on the Thread CoAP Bridge add-on**

2. **Go to the Configuration tab**

3. **Set your MQTT credentials:**
   ```yaml
   mqtt_host: core-mosquitto
   mqtt_port: 1883
   mqtt_user: homeassistant
   mqtt_password: your_mqtt_password
   discovery_interval: 60
   log_level: info
   thread_interface: wpan0
   multicast_address: ff03::fd
   ```

4. **Save the configuration**

5. **Go to the Info tab**

6. **Start the add-on**

7. **Check the Log tab** to verify it started successfully

### Verification

1. **Check OTBR is running:**
   - Settings → Add-ons → OpenThread Border Router
   - Should show "Running"

2. **Check Thread network status:**
   ```bash
   # SSH into HA
   ot-ctl state
   # Should show: leader, router, or child
   ```

3. **Verify MQTT broker:**
   - Settings → Add-ons → Mosquitto broker
   - Should show "Running"

4. **Commission a test device:**
   ```bash
   # Enable Thread joiner on device
   # Then on OTBR:
   ot-ctl commissioner start
   ot-ctl commissioner joiner add * J01NME 120
   ```

5. **Watch the bridge logs:**
   - Settings → Add-ons → Thread CoAP Bridge
   - Log tab
   - Should see discovery attempts and device registration

6. **Check Home Assistant:**
   - Settings → Devices & Services
   - Devices should appear with "Thread Sensor" prefix
   - Entities should be created automatically

## Troubleshooting

### Add-on won't start

1. **Check logs:**
   - Look for error messages in the Log tab
   - Common issues:
     - MQTT broker not running
     - Invalid configuration
     - Python dependency errors

2. **Verify dependencies:**
   - Mosquitto broker must be started first
   - OTBR should be running

3. **Check configuration:**
   - MQTT credentials correct?
   - Network settings valid?

### Devices not discovered

1. **Verify Thread network:**
   ```bash
   ot-ctl state
   ot-ctl netdata show
   ```

2. **Check device is joined:**
   ```bash
   ot-ctl child list
   # Or on the device itself:
   # ot-ctl ipaddr
   ```

3. **Test manual CoAP request:**
   ```bash
   # Install aiocoap-client
   pip3 install aiocoap
   
   # Query device
   aiocoap-client -m GET coap://[device-ipv6]/.well-known/core
   ```

4. **Enable debug logging:**
   - Configuration tab
   - Set `log_level: debug`
   - Restart add-on
   - Check logs for detailed discovery attempts

### Entities not appearing in HA

1. **Check MQTT topics:**
   - Install MQTT Explorer
   - Connect to broker
   - Look for topics under `homeassistant/`

2. **Verify MQTT Discovery is enabled:**
   - Settings → Devices & Services → MQTT
   - Check "Enable discovery" is ON

3. **Check Home Assistant logs:**
   - Settings → System → Logs
   - Look for MQTT-related errors

4. **Restart Home Assistant:**
   - Settings → System → Restart

## Updating the Add-on

### Local Installation
```bash
cd /addons/thread-coap-bridge
git pull
# Or copy new files manually
```

Then in Home Assistant:
- Go to add-on page
- Click **Rebuild**

### GitHub Repository
- Updates appear automatically in HA
- Click **Update** button when available

## Uninstalling

1. **Stop the add-on**
2. **Click Uninstall**
3. **Remove repository** (optional)
   - Add-on Store → menu (⋮) → Repositories
   - Remove the repository URL

## Next Steps

After successful installation:

1. **Commission your devices** - Use Thread Joiner credentials
2. **Configure entities in HA** - Customize names, add to dashboards
3. **Create automations** - Use device entities in automations
4. **Monitor logs** - Watch for any errors or warnings
5. **Optimize settings** - Adjust discovery interval for your needs

## Getting Help

- **GitHub Issues:** https://github.com/yourusername/ha-addon-thread-coap-bridge/issues
- **Home Assistant Community:** https://community.home-assistant.io/
- **Documentation:** See DOCS.md and README.md
