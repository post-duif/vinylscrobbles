#!/usr/bin/env python3
"""
Vinyl Recognition System - Main Application

Coordinates audio processing, music recognition, and scrobbling for automated
vinyl music recognition and Last.fm scrobbling.
"""

import asyncio
import signal
import sys
import time
import logging
import threading
import os
from pathlib import Path
from typing import Optional

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config_manager import initialize_config
from src.audio_processor import AudioProcessor
from src.music_recognizer import MusicRecognizer
from src.lastfm_scrobbler import LastFMScrobbler
from src.duplicate_detector import DuplicateDetector
from src.database import DatabaseManager

# Ensure logs directory exists
logs_dir = Path(__file__).parent / 'logs'
logs_dir.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(logs_dir / 'vinyl_recognizer.log'))
    ]
)

logger = logging.getLogger(__name__)


class VinylRecognitionSystem:
    """Main application class that coordinates all components."""
    
    def __init__(self):
        """Initialize the vinyl recognition system."""
        logger.info("Initializing Vinyl Recognition System...")
        
        # Initialize configuration
        self.config = initialize_config()
        
        # Initialize components
        self.database = DatabaseManager()
        self.duplicate_detector = DuplicateDetector(self.database)
        self.lastfm_scrobbler = LastFMScrobbler(self.database)
        self.music_recognizer = MusicRecognizer()
        self.audio_processor = AudioProcessor(on_track_detected=self.on_track_detected)
        
        # System state
        self.running = False
        self.stats = {
            'start_time': None,
            'tracks_processed': 0,
            'tracks_recognized': 0,
            'tracks_scrobbled': 0,
            'duplicates_detected': 0,
            'errors': 0
        }
        
        # Threading
        self._maintenance_thread = None
        self._shutdown_event = threading.Event()
        
        logger.info("Vinyl Recognition System initialized")
    
    def start(self):
        """Start the vinyl recognition system."""
        if self.running:
            logger.warning("System is already running")
            return
        
        logger.info("Starting Vinyl Recognition System...")
        
        try:
            # Check system readiness
            self._check_system_readiness()
            
            # Start components
            self.running = True
            self.stats['start_time'] = time.time()
            
            # Start Last.fm scrobbler
            self.lastfm_scrobbler.start_scrobble_processor()
            
            # Start audio monitoring
            self.audio_processor.start_monitoring()
            
            # Start maintenance thread
            self._start_maintenance_thread()
            
            logger.info("Vinyl Recognition System started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start system: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop the vinyl recognition system."""
        if not self.running:
            return
        
        logger.info("Stopping Vinyl Recognition System...")
        
        self.running = False
        self._shutdown_event.set()
        
        # Stop audio processing
        try:
            self.audio_processor.stop_monitoring()
        except Exception as e:
            logger.error(f"Error stopping audio processor: {e}")
        
        # Stop scrobbler
        try:
            self.lastfm_scrobbler.stop_scrobble_processor()
        except Exception as e:
            logger.error(f"Error stopping scrobbler: {e}")
        
        # Stop maintenance thread
        if self._maintenance_thread and self._maintenance_thread.is_alive():
            self._maintenance_thread.join(timeout=5.0)
        
        # Cleanup components
        try:
            self.audio_processor.cleanup()
            self.lastfm_scrobbler.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        logger.info("Vinyl Recognition System stopped")
    
    def _check_system_readiness(self):
        """Check if system is ready to start."""
        issues = []
        
        # Check audio configuration
        audio_status = self.audio_processor.get_status()
        if not audio_status.get('device_name'):
            issues.append("Audio device not configured")
        
        # Check recognition providers
        provider_status = self.music_recognizer.get_provider_status()
        available_providers = [name for name, status in provider_status['providers'].items() 
                             if status['available']]
        if not available_providers:
            issues.append("No recognition providers available")
        
        # Check Last.fm configuration (warning only)
        lastfm_status = self.lastfm_scrobbler.get_status()
        if not lastfm_status['available']:
            logger.warning("Last.fm scrobbling not available - check configuration")
        
        if issues:
            raise RuntimeError(f"System not ready: {', '.join(issues)}")
        
        logger.info(f"System ready - providers: {available_providers}, "
                   f"Last.fm: {'available' if lastfm_status['available'] else 'unavailable'}")
    
    def on_track_detected(self, audio_file: str):
        """
        Handle detected audio track.
        
        Args:
            audio_file: Path to detected audio file
        """
        logger.info(f"Processing detected track: {audio_file}")
        self.stats['tracks_processed'] += 1
        
        try:
            # Run recognition asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                recognition_result = loop.run_until_complete(
                    self.music_recognizer.recognize_track(audio_file)
                )
            finally:
                loop.close()
            
            if recognition_result.success:
                self.stats['tracks_recognized'] += 1
                logger.info(f"Track recognized: {recognition_result.artist} - {recognition_result.title} "
                           f"(confidence: {recognition_result.confidence:.2f}, provider: {recognition_result.provider})")
                
                # Check for duplicates
                duplicate_check = self.duplicate_detector.is_duplicate(recognition_result)
                
                if duplicate_check.is_duplicate:
                    self.stats['duplicates_detected'] += 1
                    logger.info(f"Duplicate track detected, skipping scrobble: "
                               f"{recognition_result.artist} - {recognition_result.title} "
                               f"(last seen {duplicate_check.time_since_last}s ago, "
                               f"confidence: {duplicate_check.confidence:.2f})")
                    return
                
                # Add to duplicate cache
                self.duplicate_detector.add_track(recognition_result)
                
                # Queue for scrobbling
                if self.lastfm_scrobbler.queue_scrobble(recognition_result):
                    self.stats['tracks_scrobbled'] += 1
                    logger.info(f"Track queued for scrobbling: {recognition_result.artist} - {recognition_result.title}")
                else:
                    logger.warning(f"Failed to queue track for scrobbling: {recognition_result.artist} - {recognition_result.title}")
            
            else:
                logger.info(f"Track recognition failed: {recognition_result.error_message}")
        
        except Exception as e:
            logger.error(f"Error processing track: {e}")
            self.stats['errors'] += 1
    
    def _start_maintenance_thread(self):
        """Start the maintenance thread."""
        self._maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self._maintenance_thread.start()
    
    def _maintenance_loop(self):
        """Maintenance loop for periodic tasks."""
        logger.info("Maintenance thread started")
        
        while self.running and not self._shutdown_event.is_set():
            try:
                # Cleanup expired duplicates
                self.duplicate_detector.cleanup_expired()
                
                # Collect system statistics
                self._collect_system_stats()
                
                # Wait for next maintenance cycle
                if self._shutdown_event.wait(timeout=300):  # 5 minutes
                    break
                    
            except Exception as e:
                logger.error(f"Error in maintenance loop: {e}")
                time.sleep(60)  # Wait longer on error
        
        logger.info("Maintenance thread stopped")
    
    def _collect_system_stats(self):
        """Collect and store system statistics."""
        try:
            import psutil
            
            # System stats
            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Temperature (Raspberry Pi specific)
            temperature = None
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temperature = float(f.read().strip()) / 1000.0
            except:
                pass
            
            stats = {
                'cpu_usage': cpu_usage,
                'memory_usage': memory.percent,
                'disk_usage': disk.percent,
                'temperature': temperature,
                'recognition_count': self.stats['tracks_recognized'],
                'scrobble_count': self.stats['tracks_scrobbled'],
                'error_count': self.stats['errors']
            }
            
            self.database.add_system_stats(stats)
            
        except ImportError:
            logger.debug("psutil not available, skipping system stats collection")
        except Exception as e:
            logger.error(f"Error collecting system stats: {e}")
    
    def get_status(self) -> dict:
        """Get comprehensive system status."""
        uptime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        
        return {
            'running': self.running,
            'uptime': uptime,
            'stats': self.stats.copy(),
            'audio': self.audio_processor.get_status(),
            'recognition': self.music_recognizer.get_provider_status(),
            'scrobbling': self.lastfm_scrobbler.get_status(),
            'duplicate_detection': self.duplicate_detector.get_cache_stats(),
            'database': self.database.get_database_stats()
        }
    
    def test_components(self) -> dict:
        """Test all system components."""
        results = {}
        
        # Test audio
        try:
            success, message, stats = self.audio_processor.test_audio_input(duration=3.0)
            results['audio'] = {
                'status': 'success' if success else 'error',
                'message': message,
                'stats': stats
            }
        except Exception as e:
            results['audio'] = {
                'status': 'error',
                'message': str(e)
            }
        
        # Test recognition providers
        results['recognition'] = self.music_recognizer.test_providers()
        
        # Test Last.fm
        results['lastfm'] = self.lastfm_scrobbler.test_connection()
        
        # Test database
        try:
            db_stats = self.database.get_database_stats()
            results['database'] = {
                'status': 'success',
                'message': f"Database operational with {db_stats.get('scrobble_history_count', 0)} scrobbles",
                'stats': db_stats
            }
        except Exception as e:
            results['database'] = {
                'status': 'error',
                'message': str(e)
            }
        
        return results


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'system'):
        signal_handler.system.stop()
    sys.exit(0)


def main():
    """Main entry point."""
    print("🎵 Vinyl Recognition System")
    print("=" * 50)
    
    # Create system instance
    system = VinylRecognitionSystem()
    signal_handler.system = system
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start system
        system.start()
        
        print(f"System started successfully!")
        print(f"Audio device: {system.audio_processor.device_name}")
        print(f"Recognition providers: {system.music_recognizer.provider_order}")
        print(f"Last.fm: {'enabled' if system.lastfm_scrobbler.is_available() else 'disabled'}")
        print(f"Duplicate detection: {'enabled' if system.duplicate_detector.enabled else 'disabled'}")
        print("")
        print("Monitoring for vinyl tracks... (Ctrl+C to stop)")
        print("=" * 50)
        
        # Keep running until signal
        while system.running:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"System error: {e}")
        return 1
    finally:
        system.stop()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())