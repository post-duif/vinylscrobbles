# 🎵 Vinyl Recognition System - Quick Start Guide

This guide walks you through getting the Vinyl Recognition System up and running on your Raspberry Pi.

## 📋 Setup Checklist

### 1. Initial Configuration
```bash
cd ~/vinylscrobbles

# Copy example configuration files
cp config/config.example.json config/config.json
cp config/secrets.example.env config/secrets.env
```

Edit `config/config.json` with your settings:
- Audio device name
- Recognition provider API keys (AudD, Shazam)
- Web server port and host

Edit `config/secrets.env` with your API credentials:
```
LASTFM_API_KEY=your_api_key
LASTFM_API_SECRET=your_api_secret
```

### 2. Last.fm Authentication (One-time setup)
```bash
cd ~/vinylscrobbles
sudo python3 scripts/lastfm_auth.py
```

**On a headless Raspberry Pi** (no display):
1. The script will display an authorization URL
2. Copy the URL from the terminal
3. On your **laptop/desktop**, paste it into your browser
4. Log in to Last.fm and click "Yes, allow access"
5. Return to the Pi terminal and press Enter

**After successful authorization**, your session key will be automatically saved to `config/secrets.env`.

### 3. Test Last.fm Connection
```bash
python3 scripts/test_lastfm.py
```

Expected output:
```
🎵 Last.fm Connection Test
==================================================

📋 Loading configuration...
✅ Configuration loaded successfully

🔐 Checking API credentials...
✅ API Key found: 3879a5b6...
✅ API Secret found: abc123de...
✅ Session Key found: 1234567...

🔗 Initializing Last.fm scrobbler...
✅ Scrobbler initialized

🔑 Checking authentication...
✅ Last.fm authentication successful
   Authenticated as: your_username

📊 Scrobbler Status:
   Enabled: True
   Available: True
   Queue size: 0

✅ Last.fm connection is ready!
```

## 🚀 Running the System

### Option 1: Run from Terminal (for testing)
```bash
cd ~/vinylscrobbles
sudo python3 scripts/start_web_server.py
```

This will:
- Start the vinyl recognition system
- Launch the web interface
- Monitor audio input continuously
- Display status in the terminal

Access the dashboard at: `http://your-pi-ip:5000`

### Option 2: Run as Background Service (production)
```bash
# Enable the systemd service
sudo systemctl enable vinyl-recognition.service

# Start the service
sudo systemctl start vinyl-recognition.service

# Check status
sudo systemctl status vinyl-recognition.service

# View logs
sudo journalctl -u vinyl-recognition.service -f
```

### Option 3: Run with Screen/tmux (manual)
```bash
screen -S vinyl
cd ~/vinylscrobbles
sudo python3 scripts/start_web_server.py

# Detach with Ctrl+A then D
```

## 🔍 Troubleshooting

### Configuration Not Found
```
Failed to load configuration: No configuration file found in config
```
**Solution:** Copy the example files:
```bash
cp config/config.example.json config/config.json
cp config/secrets.example.env config/secrets.env
```

### Last.fm Authentication Failed
```
❌ Error getting session key: 400 Client Error: Bad Request
```
**Causes and solutions:**
1. **Authorization not completed**: Go back to Step 2 and properly authorize on Last.fm
2. **Session key expired**: Run `python3 scripts/lastfm_auth.py` again
3. **Wrong API credentials**: Check `config/secrets.env` for correct keys

### Web Server Shows Nginx Error
**You must start the application**, not access a plain nginx server:
```bash
sudo python3 scripts/start_web_server.py
```

The web interface runs on port 5000 by default, not the standard HTTP port.

### Audio Device Not Detected
Check your configuration:
```bash
# List available audio devices
python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

Update the device name in `config/config.json`:
```json
{
  "audio": {
    "device_name": "USB Audio Device",
    ...
  }
}
```

### Recognition Providers Not Available
Check your API credentials in `config/secrets.env`:
```bash
cat config/secrets.env
```

Ensure you have:
- `AUDD_API_TOKEN` for AudD
- `SHAZAM_API_KEY` for Shazam

## 📊 Monitoring

### Real-time Dashboard
Open in your browser: `http://your-pi-ip:5000`

Shows:
- Currently recognized tracks
- Scrobble history
- System stats (CPU, memory, temperature)
- Recognition confidence scores
- Duplicate detection info

### Terminal Logs
```bash
# View live logs
sudo python3 scripts/start_web_server.py

# Or from systemd service
sudo journalctl -u vinyl-recognition.service -f
```

### Test System Components
```bash
python3 scripts/test_lastfm.py
```

## 🔧 Configuration Tips

### Audio Levels
- Keep USB audio interface gain **LOW** to avoid clipping
- Monitor levels before starting
- Adjust in your preamp if needed

### Recognition Providers
Edit `config/config.json` to set provider priority:
```json
{
  "recognition": {
    "providers": {
      "order": ["audd", "shazam"],
      "audd": {"enabled": true},
      "shazam": {"enabled": true}
    }
  }
}
```

### Duplicate Detection
Prevent re-scrobbling the same track:
```json
{
  "duplicate_detection": {
    "enabled": true,
    "cache_duration": 3600,
    "confidence_threshold": 0.8
  }
}
```

### Web Server
Change host/port in `config/config.json`:
```json
{
  "web_server": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  }
}
```

## 📝 File Structure

```
vinylscrobbles/
├── config/
│   ├── config.json           ← Your configuration
│   ├── secrets.env           ← Your API keys
│   └── *.example.*           ← Templates
├── scripts/
│   ├── lastfm_auth.py        ← Authentication setup
│   ├── test_lastfm.py        ← Test Last.fm connection
│   └── start_web_server.py   ← Start the system
├── src/
│   ├── config_manager.py
│   ├── lastfm_scrobbler.py
│   ├── music_recognizer.py
│   └── ...
└── vinyl_recognizer.py       ← Main application
```

## 🆘 Getting Help

1. **Check logs**: `sudo journalctl -u vinyl-recognition.service`
2. **Test components**: `python3 scripts/test_lastfm.py`
3. **Review configuration**: `cat config/config.json`
4. **Check Last.fm**: Verify session in `config/secrets.env`

## 🎉 You're Ready!

Once everything is set up:
1. Play a vinyl record
2. The system automatically recognizes and scrobbles
3. Check your Last.fm profile to see the scrobbles
4. Monitor in the web dashboard at `http://your-pi-ip:5000`

Enjoy your vinyl!
