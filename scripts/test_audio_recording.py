#!/usr/bin/env python3
"""
Direct Audio Recording Test

Records 10 seconds of audio directly from your USB device to test if audio is being captured.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))

import pyaudio
import numpy as np
import wave

def record_audio_test(duration=10, output_file="/tmp/test_recording.wav"):
    """Record audio directly from the USB device."""
    
    print("🎤 Audio Recording Test")
    print("=" * 50)
    print(f"Recording for {duration} seconds...")
    print("Play some audio or speak into your microphone")
    print()
    
    # PyAudio setup
    CHUNK = 4096
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 44100
    
    p = pyaudio.PyAudio()
    
    # List available devices
    print("📡 Available audio devices:")
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"  {i}: {info['name']} (inputs: {info['maxInputChannels']})")
    print()
    
    # Find USB Audio device
    device_index = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if 'USB' in info['name'] and info['maxInputChannels'] > 0:
            device_index = i
            print(f"✅ Using device: {info['name']} (index: {i})")
            break
    
    if device_index is None:
        print("❌ No USB audio device found!")
        print("Please connect your USB audio interface and try again.")
        p.terminate()
        return False
    
    try:
        # Open audio stream
        stream = p.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       input=True,
                       input_device_index=device_index,
                       frames_per_buffer=CHUNK)
        
        print(f"📝 Recording to: {output_file}")
        print()
        
        frames = []
        for i in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK)
            frames.append(data)
            
            # Show recording progress
            progress = int((i / (RATE / CHUNK * duration)) * 100)
            print(f"  Progress: {progress}%", end='\r')
        
        print(f"  Progress: 100%")
        print()
        
        stream.stop_stream()
        stream.close()
        
        # Save to WAV file
        with wave.open(output_file, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
        
        p.terminate()
        
        # Analyze the recording
        print("✅ Recording saved!")
        print()
        print("📊 Analyzing audio...")
        
        with wave.open(output_file, 'rb') as wf:
            audio_data = wf.readframes(wf.getnframes())
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            
            rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2)) / 32768.0
            peak = np.max(np.abs(audio_np)) / 32768.0
            
            print(f"   RMS level: {rms:.4f}")
            print(f"   Peak level: {peak:.4f}")
            print(f"   File size: {os.path.getsize(output_file) / 1024:.1f} KB")
            
            if rms < 0.01:
                print("\n❌ Audio is VERY QUIET - almost silent")
                print("   Check:")
                print("   - USB audio device is connected")
                print("   - Turntable/preamp is plugged into USB device")
                print("   - Audio levels are not turned down")
                return False
            
            if rms < 0.05:
                print("\n⚠️  Audio is quiet")
                print("   Consider raising the audio level on your preamp")
            else:
                print("\n✅ Audio level looks good!")
            
            return True
    
    except Exception as e:
        print(f"❌ Error during recording: {e}")
        p.terminate()
        return False


if __name__ == '__main__':
    success = record_audio_test()
    
    if success:
        print("\n✅ Audio recording test successful!")
        print(f"   File: /tmp/test_recording.wav")
        print(f"   You can now run: python3 vinyl_recognizer.py")
    else:
        print("\n❌ Audio recording test failed!")
        print("   Check your USB audio device and connections")
    
    sys.exit(0 if success else 1)
