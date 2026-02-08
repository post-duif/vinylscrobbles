#!/usr/bin/env python3
"""
Vinyl Recognition System - Web Server Startup

Starts the Flask web interface for monitoring and configuration.
Access the dashboard at http://your-pi-ip:5000
"""

import os
import sys
import logging
from pathlib import Path

# Add src directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

try:
    from config_manager import initialize_config
    from vinyl_recognizer import VinylRecognitionSystem
except ImportError as e:
    print(f"Error: Could not import required modules: {e}")
    sys.exit(1)


def start_web_server():
    """Start the vinyl recognition system with web interface."""
    print("🎵 Vinyl Recognition System - Web Server")
    print("=" * 50)
    print()
    
    # Initialize configuration
    print("📋 Loading configuration...")
    config_dir = os.path.join(project_root, 'config')
    try:
        config = initialize_config(config_dir)
        print("✅ Configuration loaded")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False
    
    # Initialize system
    print("🚀 Initializing vinyl recognition system...")
    try:
        system = VinylRecognitionSystem()
        print("✅ System initialized")
    except Exception as e:
        print(f"❌ Failed to initialize system: {e}")
        logger.exception("System initialization error")
        return False
    
    # Get web configuration
    web_config = config.get_web_config()
    host = web_config.get('host', '0.0.0.0')
    port = web_config.get('port', 5000)
    
    print()
    print("🌐 Web Interface:")
    print(f"   URL: http://localhost:{port}")
    print(f"   Host: {host}")
    print()
    
    # Display system status
    print("📊 System Status:")
    try:
        status = system.get_status()
        print(f"   Audio device: {status['audio'].get('device_name', 'Not configured')}")
        print(f"   Last.fm: {'Available' if status['scrobbling']['available'] else 'Not available'}")
        providers = status['recognition']['providers']
        available = [p for p, s in providers.items() if s['available']]
        print(f"   Recognition providers: {', '.join(available) if available else 'None available'}")
    except Exception as e:
        logger.warning(f"Could not retrieve status: {e}")
    
    print()
    print("🎧 System is running!")
    print("Monitoring vinyl tracks and audio input...")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        system.run()
    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down...")
        system.stop()
        print("✅ System stopped")
    except Exception as e:
        print(f"\n❌ System error: {e}")
        logger.exception("System error")
        return False
    
    return True


if __name__ == '__main__':
    try:
        success = start_web_server()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
