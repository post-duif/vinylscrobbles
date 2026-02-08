#!/usr/bin/env python3
"""
Audio File Diagnostic Tool

Checks if WAV files have actual audio data and displays audio characteristics.
"""

import sys
import os
import wave
import numpy as np
from pathlib import Path

def check_wav_file(filepath):
    """Check if a WAV file has audio data."""
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return False
    
    file_size = os.path.getsize(filepath)
    print(f"📁 File: {filepath}")
    print(f"📊 File size: {file_size / 1024:.1f} KB")
    
    if file_size < 100:
        print("❌ File is too small - likely empty or corrupt")
        return False
    
    try:
        with wave.open(filepath, 'rb') as wav_file:
            # Get audio parameters
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            n_frames = wav_file.getnframes()
            
            duration_sec = n_frames / framerate
            
            print(f"\n🎵 Audio Parameters:")
            print(f"   Channels: {n_channels}")
            print(f"   Sample width: {sample_width} bytes ({sample_width * 8}-bit)")
            print(f"   Sample rate: {framerate} Hz")
            print(f"   Total frames: {n_frames}")
            print(f"   Duration: {duration_sec:.2f} seconds")
            
            # Read audio data
            audio_data = wav_file.readframes(n_frames)
            
            if not audio_data:
                print("❌ No audio data found in file")
                return False
            
            # Convert to numpy array for analysis
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate statistics
            rms = np.sqrt(np.mean(audio_np ** 2))
            peak = np.max(np.abs(audio_np))
            mean = np.mean(audio_np)
            
            print(f"\n📈 Audio Statistics:")
            print(f"   RMS (volume): {rms:.0f}")
            print(f"   Peak amplitude: {peak}")
            print(f"   Mean: {mean:.0f}")
            
            # Check if audio is mostly silent
            silence_threshold = 1000  # Arbitrary threshold for "silence"
            silent_frames = np.sum(np.abs(audio_np) < silence_threshold)
            silence_percentage = (silent_frames / len(audio_np)) * 100
            
            print(f"   Silence percentage: {silence_percentage:.1f}%")
            
            if rms < 100:
                print("\n⚠️  Audio is very quiet (mostly silent)")
                print("   Possible causes:")
                print("   - USB audio device not connected or not selected")
                print("   - Preamp/turntable not plugged in")
                print("   - Audio gain too low")
                return False
            
            if silence_percentage > 80:
                print("\n⚠️  Audio is mostly silent")
                print("   Check your turntable and preamp connections")
                return False
            
            print("\n✅ Audio file appears valid!")
            return True
    
    except wave.Error as e:
        print(f"❌ Not a valid WAV file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python3 check_audio.py <path_to_wav_file>")
        print("\nExample:")
        print("  python3 check_audio.py /tmp/vinyl_track_xyz.wav")
        print("\nTo find recent WAV files:")
        print("  ls -lt /tmp/vinyl_track_*.wav | head -5")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success = check_wav_file(filepath)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
