#!/usr/bin/env python3
"""
Last.fm Connection Test Script

Tests whether the Last.fm connection and session key are working properly.
"""

import os
import sys
from pathlib import Path

# Add src directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))

try:
    from config_manager import initialize_config
    from lastfm_scrobbler import LastFMScrobbler
except ImportError as e:
    print(f"Error: Could not import required modules: {e}")
    sys.exit(1)


def test_lastfm_connection():
    """Test Last.fm connection and authentication."""
    print("🎵 Last.fm Connection Test")
    print("=" * 50)
    print()
    
    # Initialize configuration
    print("📋 Loading configuration...")
    config_dir = os.path.join(project_root, 'config')
    try:
        config = initialize_config(config_dir)
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False
    
    print()
    
    # Check secrets
    print("🔐 Checking API credentials...")
    api_key = config.get_secret('LASTFM_API_KEY')
    api_secret = config.get_secret('LASTFM_API_SECRET')
    session_key = config.get_secret('LASTFM_SESSION_KEY')
    
    if not api_key:
        print("❌ LASTFM_API_KEY not found in secrets")
        return False
    print(f"✅ API Key found: {api_key[:8]}...")
    
    if not api_secret:
        print("❌ LASTFM_API_SECRET not found in secrets")
        return False
    print(f"✅ API Secret found: {api_secret[:8]}...")
    
    if not session_key:
        print("⚠️  LASTFM_SESSION_KEY not found - may not be able to scrobble")
        print("   Run: python3 lastfm_auth.py")
    else:
        print(f"✅ Session Key found: {session_key[:8]}...")
    
    print()
    
    # Initialize scrobbler
    print("🔗 Initializing Last.fm scrobbler...")
    try:
        scrobbler = LastFMScrobbler()
        print("✅ Scrobbler initialized")
    except Exception as e:
        print(f"❌ Failed to initialize scrobbler: {e}")
        return False
    
    print()
    
    # Check if authenticated
    print("🔑 Checking authentication...")
    if scrobbler._authenticated:
        print("✅ Last.fm authentication successful")
        if scrobbler.user:
            print(f"   Authenticated as: {scrobbler.user.get_name()}")
    else:
        print("⚠️  Not authenticated with Last.fm")
        if session_key:
            print("   Session key exists but authentication failed")
            print("   Possible causes:")
            print("   - Session key has expired")
            print("   - Network connectivity issue")
            print("   - API key/secret mismatch")
            print()
            print("   Try running authentication again:")
            print("   python3 lastfm_auth.py")
        else:
            print("   No session key found - complete authentication first:")
            print("   python3 lastfm_auth.py")
    
    print()
    
    # Check scrobbler status
    print("📊 Scrobbler Status:")
    print(f"   Enabled: {scrobbler.enabled}")
    print(f"   Available: {scrobbler.is_available()}")
    print(f"   Queue size: {len(scrobbler.scrobble_queue) if hasattr(scrobbler, 'scrobble_queue') else 'N/A'}")
    
    print()
    
    if scrobbler.is_available():
        print("✅ Last.fm connection is ready!")
        return True
    else:
        print("❌ Last.fm connection is not ready")
        return False


if __name__ == '__main__':
    try:
        success = test_lastfm_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
