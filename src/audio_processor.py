"""
Audio Processor

Handles real-time audio capture, silence detection, and audio preprocessing
for the vinyl recognition system.
"""

import pyaudio
import numpy as np
import wave
import threading
import time
import logging
from typing import Optional, Callable, Tuple
from pathlib import Path
import tempfile
import os

from config_manager import get_config

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Manages audio capture and processing for vinyl recognition."""
    
    def __init__(self, on_track_detected: Optional[Callable[[str], None]] = None):
        """
        Initialize the audio processor.
        
        Args:
            on_track_detected: Callback function when a track is detected
        """
        # Defensive: ensure all attributes exist even if init fails
        self._audio_thread = None
        self.stream = None
        self.audio = None
        self.input_device_index = None
        self.is_recording = False
        self.is_running = False
        self.current_recording = []
        self.silence_start_time = None
        self.music_start_time = None
        self.last_track_end_time = 0
        self._lock = threading.Lock()
        self.on_track_detected = on_track_detected
        # Now proceed with normal initialization
        self.config = get_config()
        self.audio_config = self.config.get_audio_config()
        
        # Audio settings
        self.device_name = self.audio_config.get('device_name', 'USB Audio CODEC')
        self.sample_rate = self.audio_config.get('sample_rate', 44100)
        self.chunk_size = self.audio_config.get('chunk_size', 4096)
        self.channels = self.audio_config.get('channels', 2)
        
        # Map format string to pyaudio format constant (e.g., "int16" -> pyaudio.paInt16)
        format_str = self.audio_config.get("format", "int16").lower()
        # Convert "int16" -> "Int16" to match PyAudio's naming convention (paInt16)
        format_name = ''.join([format_str[0].upper(), format_str[1:]])
        self.format = getattr(pyaudio, f'pa{format_name}')
        
        # Detection settings
        self.silence_threshold = self.audio_config.get('silence_threshold', 0.01)
        self.silence_duration = self.audio_config.get('silence_duration', 2.0)
        self.recording_duration = self.audio_config.get('recording_duration', 30.0)
        self.max_recording_duration = self.audio_config.get('max_recording_duration', 120.0)
        
        # State management
        self.is_recording = False
        self.is_running = False
        self.current_recording = []
        self.silence_start_time = None
        self.music_start_time = None
        self.last_track_end_time = 0
        
        # Threading
        self._audio_thread = None
        self._lock = threading.Lock()
        
        # PyAudio instance
        self.audio = None
        self.input_device_index = None
        
        self._initialize_audio()
    
    def _initialize_audio(self):
        """Initialize PyAudio and find the correct input device."""
        try:
            self.audio = pyaudio.PyAudio()
            self.input_device_index = self._find_input_device()
            
            if self.input_device_index is None:
                raise RuntimeError(f"Audio device '{self.device_name}' not found")
                
            logger.info(f"Audio device initialized: {self.device_name} (index: {self.input_device_index})")
            
        except Exception as e:
            logger.error(f"Failed to initialize audio: {e}")
            raise
    
    def _find_input_device(self) -> Optional[int]:
        """Find the input device index by name."""
        device_count = self.audio.get_device_count()
        
        for i in range(device_count):
            device_info = self.audio.get_device_info_by_index(i)
            if (self.device_name.lower() in device_info['name'].lower() and 
                device_info['maxInputChannels'] > 0):
                return i
        
        # Fallback: return default input device
        try:
            default_device = self.audio.get_default_input_device_info()
            logger.warning(f"Using default input device: {default_device['name']}")
            return default_device['index']
        except:
            return None
    
    def start_monitoring(self):
        """Start audio monitoring in a separate thread."""
        if self.is_running:
            logger.warning("Audio monitoring is already running")
            return
        
        self.is_running = True
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._audio_thread.start()
        logger.info("Audio monitoring started")
    
    def stop_monitoring(self):
        """Stop audio monitoring."""
        self.is_running = False
        
        if self._audio_thread and self._audio_thread.is_alive():
            self._audio_thread.join(timeout=5.0)
        
        self._close_stream()
        logger.info("Audio monitoring stopped")
    
    def _audio_loop(self):
        """Main audio processing loop."""
        try:
            self._open_stream()
            
            while self.is_running:
                if self.stream and self.stream.is_active():
                    try:
                        # Read audio data
                        data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        
                        # Process audio data
                        self._process_audio_chunk(audio_data)
                        
                    except Exception as e:
                        logger.error(f"Error reading audio data: {e}")
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Audio loop error: {e}")
        finally:
            self._close_stream()
    
    def _open_stream(self):
        """Open the audio input stream."""
        try:
            self.stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=None
            )
            logger.info("Audio stream opened")
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            raise
    
    def _close_stream(self):
        """Close the audio stream."""
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
                logger.debug("Audio stream closed")
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
    
    def _process_audio_chunk(self, audio_data: np.ndarray):
        """Process a chunk of audio data for silence/music detection."""
        # Calculate RMS (Root Mean Square) for volume level
        if len(audio_data) > 0:
            rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)) / 32768.0
        else:
            rms = 0.0
        
        current_time = time.time()
        is_silent = rms < self.silence_threshold
        
        with self._lock:
            if is_silent:
                self._handle_silence(current_time)
            else:
                self._handle_music(current_time, audio_data)
    
    def _handle_silence(self, current_time: float):
        """Handle detected silence."""
        if self.silence_start_time is None:
            self.silence_start_time = current_time
        
        silence_duration = current_time - self.silence_start_time
        
        # If we were recording and silence has lasted long enough, finish recording
        if (self.is_recording and 
            silence_duration >= self.silence_duration and 
            len(self.current_recording) > 0):
            self._finish_recording()
        
        # Reset music start time
        self.music_start_time = None
    
    def _handle_music(self, current_time: float, audio_data: np.ndarray):
        """Handle detected music."""
        # Reset silence tracking
        self.silence_start_time = None
        
        # Start tracking music if not already
        if self.music_start_time is None:
            self.music_start_time = current_time
            
            # Check if enough time has passed since last track
            if current_time - self.last_track_end_time > self.silence_duration:
                self._start_recording()
        
        # Add audio data to current recording if recording
        if self.is_recording:
            self.current_recording.extend(audio_data)
            
            # Check if recording is getting too long
            recording_duration = current_time - self.music_start_time
            if recording_duration >= self.max_recording_duration:
                logger.warning(f"Recording exceeded maximum duration, finishing early")
                self._finish_recording()
    
    def _start_recording(self):
        """Start recording a new track."""
        if not self.is_recording:
            self.is_recording = True
            self.current_recording = []
            logger.info("Started recording new track")
    
    def _finish_recording(self):
        """Finish current recording and trigger recognition."""
        if not self.is_recording or len(self.current_recording) == 0:
            return
        
        self.is_recording = False
        self.last_track_end_time = time.time()
        
        # Check if recording is long enough
        recording_duration = len(self.current_recording) / (self.sample_rate * self.channels)
        
        if recording_duration < self.recording_duration:
            logger.debug(f"Recording too short ({recording_duration:.1f}s), discarding")
            self.current_recording = []
            return
        
        logger.info(f"Finished recording ({recording_duration:.1f}s), starting recognition")
        
        # Save recording and trigger recognition
        try:
            audio_file = self._save_recording(self.current_recording)
            self.current_recording = []
            
            if self.on_track_detected and audio_file:
                # Run recognition in a separate thread to avoid blocking audio processing
                recognition_thread = threading.Thread(
                    target=self.on_track_detected,
                    args=(audio_file,),
                    daemon=True
                )
                recognition_thread.start()
                
        except Exception as e:
            logger.error(f"Error processing recording: {e}")
            self.current_recording = []
    
    def _save_recording(self, audio_data: list) -> Optional[str]:
        """
        Save recorded audio data to a temporary WAV file.
        
        Args:
            audio_data: List of audio samples
            
        Returns:
            Path to saved audio file
        """
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav', prefix='vinyl_track_')
            os.close(temp_fd)
            
            # Convert audio data to numpy array
            audio_array = np.array(audio_data, dtype=np.int16)
            
            # Save as WAV file
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(self.audio.get_sample_size(self.format))
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_array.tobytes())
            
            logger.debug(f"Saved recording to {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to save recording: {e}")
            return None
    
    def get_status(self) -> dict:
        """Get current audio processor status."""
        with self._lock:
            return {
                'is_running': self.is_running,
                'is_recording': self.is_recording,
                'device_name': self.device_name,
                'sample_rate': self.sample_rate,
                'channels': self.channels,
                'silence_threshold': self.silence_threshold,
                'recording_duration': len(self.current_recording) / (self.sample_rate * self.channels) if self.current_recording else 0,
                'music_detected': self.music_start_time is not None,
                'silence_duration': (time.time() - self.silence_start_time) if self.silence_start_time else 0
            }
    
    def test_audio_input(self, duration: float = 5.0) -> Tuple[bool, str, Optional[dict]]:
        """
        Test audio input for the specified duration.
        
        Args:
            duration: Test duration in seconds
            
        Returns:
            Tuple of (success, message, stats)
        """
        try:
            if self.is_running:
                return False, "Cannot test while monitoring is active", None
            
            self._open_stream()
            
            logger.info(f"Testing audio input for {duration} seconds...")
            
            start_time = time.time()
            samples = []
            max_level = 0.0
            min_level = float('inf')
            
            while time.time() - start_time < duration:
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    
                    if len(audio_data) > 0:
                        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)) / 32768.0
                        samples.append(rms)
                        max_level = max(max_level, rms)
                        min_level = min(min_level, rms)
                        
                except Exception as e:
                    logger.error(f"Error during audio test: {e}")
                    return False, f"Audio test failed: {e}", None
            
            self._close_stream()
            
            if samples:
                avg_level = np.mean(samples)
                stats = {
                    'duration': duration,
                    'samples': len(samples),
                    'avg_level': avg_level,
                    'max_level': max_level,
                    'min_level': min_level,
                    'above_threshold': sum(1 for s in samples if s > self.silence_threshold),
                    'threshold': self.silence_threshold
                }
                
                if avg_level > 0:
                    message = f"Audio test successful. Average level: {avg_level:.4f}"
                    return True, message, stats
                else:
                    message = "No audio detected. Check connections and levels."
                    return False, message, stats
            else:
                return False, "No audio samples captured", None
                
        except Exception as e:
            self._close_stream()
            return False, f"Audio test failed: {e}", None
    
    def cleanup(self):
        """Clean up audio resources."""
        self.stop_monitoring()
        
        if self.audio:
            try:
                self.audio.terminate()
                self.audio = None
                logger.debug("PyAudio terminated")
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()