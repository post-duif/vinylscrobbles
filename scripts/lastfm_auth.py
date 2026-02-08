#!/usr/bin/env python3
"""
Last.fm Authentication Helper

This script helps you obtain a session key for Last.fm API authentication
without requiring your password to be stored in the application.
"""

import os
import sys
import hashlib
import webbrowser
from urllib.parse import urlencode
import requests

# Add src directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))

try:
    from config_manager import initialize_config
except ImportError:
    print("Error: Could not import config_manager. Make sure you're running from the project directory.")
    sys.exit(1)


class LastFMAuthenticator:
    """Handles Last.fm OAuth-style authentication flow."""
    
    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.session_key = None
        
    def load_config(self):
        """Load API credentials from configuration."""
        try:
            # Initialize config with the correct path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            config_dir = os.path.join(project_root, 'config')
            config = initialize_config(config_dir)
            self.api_key = config.get_secret('LASTFM_API_KEY')
            self.api_secret = config.get_secret('LASTFM_API_SECRET')
            
            if not self.api_key or not self.api_secret:
                print("❌ Last.fm API key and secret not found in configuration.")
                print("Please add them to config/secrets.env:")
                print("LASTFM_API_KEY=your_api_key")
                print("LASTFM_API_SECRET=your_api_secret")
                return False
                
            return True
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return False
    
    def generate_api_signature(self, params):
        """Generate API signature for Last.fm requests."""
        # Sort parameters and concatenate
        sorted_params = sorted(params.items())
        signature_string = ''.join([f"{k}{v}" for k, v in sorted_params])
        signature_string += self.api_secret
        
        # Create MD5 hash
        return hashlib.md5(signature_string.encode('utf-8')).hexdigest()
    
    def get_request_token(self):
        """Step 1: Get request token and authorization URL."""
        print("🔑 Step 1: Getting request token...")
        
        params = {
            'method': 'auth.getToken',
            'api_key': self.api_key,
            'format': 'json'
        }
        
        # Add signature
        params['api_sig'] = self.generate_api_signature(params)
        
        try:
            response = requests.get('https://ws.audioscrobbler.com/2.0/', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                print(f"❌ Last.fm API error: {data['message']}")
                return None
                
            token = data['token']
            print(f"✅ Request token obtained: {token}")
            return token
            
        except Exception as e:
            print(f"❌ Error getting request token: {e}")
            return None
    
    def authorize_token(self, token):
        """Step 2: Open browser for user authorization."""
        print("\n🌐 Step 2: User authorization...")
        
        auth_url = f"https://www.last.fm/api/auth/?api_key={self.api_key}&token={token}"
        
        print("\n📋 Authorization URL:")
        print(f"{auth_url}")
        print()
        
        # Try to open browser automatically
        browser_opened = False
        try:
            if webbrowser.open(auth_url):
                browser_opened = True
                print("✅ Browser opened automatically")
        except Exception as e:
            print(f"ℹ️  Could not open browser automatically: {e}")
        
        if not browser_opened:
            print("\n⚠️  HEADLESS SYSTEM DETECTED")
            print("Since this appears to be a headless system (no graphical display),")
            print("you need to authorize from another device:")
            print()
            print("1. Copy the authorization URL above")
            print("2. Open it on your laptop/desktop browser")
            print("3. Log in to your Last.fm account")
            print("4. Click 'Yes, allow access' to authorize this application")
            print("5. Return here and press Enter")
        
        # Wait for user confirmation
        input("\n⏳ Press Enter after you have authorized the application...")
        
    def get_session_key(self, token):
        """Step 3: Exchange authorized token for session key."""
        print("\n🔐 Step 3: Getting session key...")
        
        params = {
            'method': 'auth.getSession',
            'api_key': self.api_key,
            'token': token,
            'format': 'json'
        }
        
        # Add signature
        params['api_sig'] = self.generate_api_signature(params)
        
        try:
            response = requests.get('https://ws.audioscrobbler.com/2.0/', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                print(f"❌ Last.fm API error: {data['message']}")
                if data['error'] == 14:
                    print("This usually means you haven't authorized the token yet.")
                    print("Please make sure you clicked 'Yes, allow access' on the Last.fm website.")
                return None
                
            session = data['session']
            session_key = session['key']
            username = session['name']
            
            print(f"✅ Session key obtained for user: {username}")
            print(f"Session key: {session_key}")
            
            return session_key, username
            
        except Exception as e:
            print(f"❌ Error getting session key: {e}")
            return None
    
    def test_session_key(self, session_key):
        """Test the session key by making an authenticated request."""
        print("\n🧪 Testing session key...")
        
        params = {
            'method': 'user.getInfo',
            'api_key': self.api_key,
            'sk': session_key,
            'format': 'json'
        }
        
        # Add signature
        params['api_sig'] = self.generate_api_signature(params)
        
        try:
            response = requests.get('https://ws.audioscrobbler.com/2.0/', params=params)
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                print(f"❌ Session key test failed: {data['message']}")
                return False
                
            user = data['user']
            print(f"✅ Session key is valid!")
            print(f"   Username: {user['name']}")
            print(f"   Playcount: {user['playcount']}")
            print(f"   Country: {user.get('country', 'Unknown')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error testing session key: {e}")
            return False
    
    def save_session_key(self, session_key):
        """Save session key to secrets file."""
        print("\n💾 Saving session key...")
        
        secrets_file = os.path.join(os.path.dirname(__file__), '..', 'config', 'secrets.env')
        
        try:
            # Read existing secrets file
            lines = []
            if os.path.exists(secrets_file):
                with open(secrets_file, 'r') as f:
                    lines = f.readlines()
            
            # Update or add session key
            session_key_line = f"LASTFM_SESSION_KEY={session_key}\n"
            session_key_found = False
            
            for i, line in enumerate(lines):
                if line.startswith('LASTFM_SESSION_KEY='):
                    lines[i] = session_key_line
                    session_key_found = True
                    break
            
            if not session_key_found:
                lines.append(session_key_line)
            
            # Write back to file
            with open(secrets_file, 'w') as f:
                f.writelines(lines)
            
            print(f"✅ Session key saved to {secrets_file}")
            print("\n🎉 Authentication complete! You can now start the vinyl recognition service.")
            
        except Exception as e:
            print(f"❌ Error saving session key: {e}")
            print(f"\nPlease manually add this line to {secrets_file}:")
            print(f"LASTFM_SESSION_KEY={session_key}")
    
    def authenticate(self):
        """Run the complete authentication flow."""
        print("🎵 Last.fm Authentication Helper")
        print("=" * 40)
        print()
        
        # Load configuration
        if not self.load_config():
            return False
        
        # Step 1: Get request token
        token = self.get_request_token()
        if not token:
            return False
        
        # Step 2: User authorization
        self.authorize_token(token)
        
        # Step 3: Get session key
        result = self.get_session_key(token)
        if not result:
            return False
        
        session_key, username = result
        
        # Step 4: Test session key
        if not self.test_session_key(session_key):
            return False
        
        # Step 5: Save session key
        self.save_session_key(session_key)
        
        return True


def main():
    """Main function."""
    authenticator = LastFMAuthenticator()
    
    try:
        success = authenticator.authenticate()
        if success:
            print("\n✅ Last.fm authentication completed successfully!")
            print("You can now start the vinyl recognition service.")
        else:
            print("\n❌ Authentication failed. Please check the errors above and try again.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n❌ Authentication cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()