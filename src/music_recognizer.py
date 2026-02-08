"""
Music Recognizer

Handles music recognition using multiple API providers with configurable priority
and failover support. Supports AudD, Shazam, and extensible for additional providers.
"""

import requests
import asyncio
import aiohttp
import logging
import time
import os
import tempfile
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from pathlib import Path
import json

try:
    from shazamio import Shazam
    SHAZAM_AVAILABLE = True
except ImportError:
    SHAZAM_AVAILABLE = False
    logger.warning("shazamio not available. Install with: pip install shazamio")

from config_manager import get_config

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """Result from music recognition."""
    success: bool
    confidence: float
    provider: str
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    duration: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class BaseRecognitionProvider:
    """Base class for recognition providers."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.enabled = config.get('enabled', False)
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)
    
    async def recognize(self, audio_file: str) -> RecognitionResult:
        """Recognize music from audio file."""
        raise NotImplementedError
    
    def is_available(self) -> bool:
        """Check if provider is available and configured."""
        return self.enabled


class AudDProvider(BaseRecognitionProvider):
    """AudD music recognition provider."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('audd', config)
        self.api_url = config.get('api_url', 'https://api.audd.io/')
        self.api_key = get_config().get_secret('AUDD_API_KEY')
    
    def is_available(self) -> bool:
        """Check if AudD is available and configured."""
        return self.enabled and self.api_key is not None
    
    async def recognize(self, audio_file: str) -> RecognitionResult:
        """Recognize music using AudD API."""
        if not self.is_available():
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message="AudD API key not configured"
            )
        
        try:
            # Prepare the audio file for upload
            with open(audio_file, 'rb') as f:
                audio_data = f.read()
            
            # Prepare the request
            data = {
                'api_token': self.api_key,
                'return': 'apple_music,spotify,deezer,napster,musicbrainz'
            }
            
            files = {
                'file': ('audio.wav', audio_data, 'audio/wav')
            }
            
            # Make the API request
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                async with session.post(self.api_url, data=data, files=files) as response:
                    if response.status == 200:
                        result_data = await response.json()
                        return self._parse_audd_response(result_data)
                    else:
                        error_msg = f"AudD API error: HTTP {response.status}"
                        logger.error(error_msg)
                        return RecognitionResult(
                            success=False,
                            confidence=0.0,
                            provider=self.name,
                            error_message=error_msg
                        )
        
        except Exception as e:
            error_msg = f"AudD recognition error: {e}"
            logger.error(error_msg)
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message=error_msg
            )
    
    def _parse_audd_response(self, data: Dict[str, Any]) -> RecognitionResult:
        """Parse AudD API response."""
        try:
            if data.get('status') == 'success' and data.get('result'):
                result = data['result']
                
                # Extract basic track info
                artist = result.get('artist', '')
                title = result.get('title', '')
                album = result.get('album', '')
                
                # Calculate confidence based on available data
                confidence = 0.8  # Base confidence for successful AudD recognition
                if result.get('apple_music') or result.get('spotify'):
                    confidence = 0.9  # Higher confidence if found in major services
                
                return RecognitionResult(
                    success=True,
                    confidence=confidence,
                    provider=self.name,
                    artist=artist,
                    title=title,
                    album=album,
                    duration=result.get('duration'),
                    year=self._extract_year(result),
                    metadata=result
                )
            else:
                return RecognitionResult(
                    success=False,
                    confidence=0.0,
                    provider=self.name,
                    error_message="No match found"
                )
        
        except Exception as e:
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message=f"Failed to parse AudD response: {e}"
            )
    
    def _extract_year(self, result: Dict[str, Any]) -> Optional[int]:
        """Extract year from AudD result."""
        # Try various fields that might contain year information
        for field in ['release_date', 'year']:
            if field in result and result[field]:
                try:
                    if isinstance(result[field], str) and len(result[field]) >= 4:
                        return int(result[field][:4])
                    elif isinstance(result[field], int):
                        return result[field]
                except (ValueError, TypeError):
                    continue
        return None


class ShazamProvider(BaseRecognitionProvider):
    """Shazam music recognition provider."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__('shazam', config)
        self.shazam_client = None
        if SHAZAM_AVAILABLE:
            self.shazam_client = Shazam()
    
    def is_available(self) -> bool:
        """Check if Shazam is available."""
        return self.enabled and SHAZAM_AVAILABLE and self.shazam_client is not None
    
    async def recognize(self, audio_file: str) -> RecognitionResult:
        """Recognize music using Shazam API."""
        if not self.is_available():
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message="Shazam not available or not configured"
            )
        
        try:
            # Shazam requires the audio file path
            result_data = await self.shazam_client.recognize_song(audio_file)
            return self._parse_shazam_response(result_data)
        
        except Exception as e:
            error_msg = f"Shazam recognition error: {e}"
            logger.error(error_msg)
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message=error_msg
            )
    
    def _parse_shazam_response(self, data: Dict[str, Any]) -> RecognitionResult:
        """Parse Shazam API response."""
        try:
            if data.get('matches') and len(data['matches']) > 0:
                match = data['matches'][0]
                track = match.get('track', {})
                
                artist = track.get('subtitle', '')
                title = track.get('title', '')
                
                # Extract additional metadata
                metadata = track.get('sections', [])
                album = None
                year = None
                
                # Try to extract album and year from metadata
                for section in metadata:
                    if section.get('type') == 'SONG':
                        metadata_items = section.get('metadata', [])
                        for item in metadata_items:
                            if item.get('title') == 'Album':
                                album = item.get('text')
                            elif item.get('title') == 'Released':
                                try:
                                    year = int(item.get('text', '')[:4])
                                except (ValueError, TypeError):
                                    pass
                
                # Shazam confidence is generally high for matches
                confidence = 0.85
                
                return RecognitionResult(
                    success=True,
                    confidence=confidence,
                    provider=self.name,
                    artist=artist,
                    title=title,
                    album=album,
                    year=year,
                    metadata=data
                )
            else:
                return RecognitionResult(
                    success=False,
                    confidence=0.0,
                    provider=self.name,
                    error_message="No match found"
                )
        
        except Exception as e:
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider=self.name,
                error_message=f"Failed to parse Shazam response: {e}"
            )


class MusicRecognizer:
    """Main music recognition coordinator with multiple providers."""
    
    def __init__(self):
        self.config = get_config()
        self.recognition_config = self.config.get_recognition_config()
        
        self.min_confidence = self.recognition_config.get('min_confidence', 0.6)
        self.rate_limit_delay = self.recognition_config.get('rate_limit_delay', 1.0)
        self.last_request_time = 0
        
        # Initialize providers
        self.providers = self._initialize_providers()
        self.provider_order = self._get_provider_order()
        
        logger.info(f"Initialized music recognizer with providers: {[p.name for p in self.providers if p.is_available()]}")
    
    def _initialize_providers(self) -> List[BaseRecognitionProvider]:
        """Initialize all available recognition providers."""
        providers = []
        provider_configs = self.recognition_config.get('providers', {})
        
        # Initialize AudD provider
        if 'audd' in provider_configs:
            providers.append(AudDProvider(provider_configs['audd']))
        
        # Initialize Shazam provider
        if 'shazam' in provider_configs:
            providers.append(ShazamProvider(provider_configs['shazam']))
        
        return providers
    
    def _get_provider_order(self) -> List[str]:
        """Get the order in which to try providers."""
        configured_order = self.recognition_config.get('providers', {}).get('order', ['audd', 'shazam'])
        
        # Filter to only include available providers
        available_providers = {p.name for p in self.providers if p.is_available()}
        return [name for name in configured_order if name in available_providers]
    
    async def recognize_track(self, audio_file: str) -> RecognitionResult:
        """
        Recognize a track using available providers with failover.
        
        Args:
            audio_file: Path to audio file to recognize
            
        try:
            from shazamio import Shazam
            SHAZAM_AVAILABLE = True
        except ImportError:
            SHAZAM_AVAILABLE = False

        from config_manager import get_config

        # Initialize module logger early so import-time checks can safely log
        logger = logging.getLogger(__name__)

        # If shazamio isn't available, log a user-friendly warning
        if not SHAZAM_AVAILABLE:
            logger.warning("shazamio not available. Install with: pip install shazamio")
        
        self.last_request_time = time.time()
        
        # Try providers in order
        best_result = None
        
        for provider_name in self.provider_order:
            provider = next((p for p in self.providers if p.name == provider_name), None)
            
            if not provider or not provider.is_available():
                continue
            
            logger.info(f"Trying recognition with {provider_name}")
            
            try:
                result = await provider.recognize(audio_file)
                
                if result.success and result.confidence >= self.min_confidence:
                    logger.info(f"Recognition successful with {provider_name}: {result.artist} - {result.title} (confidence: {result.confidence:.2f})")
                    
                    # Clean up temporary file
                    self._cleanup_audio_file(audio_file)
                    return result
                
                elif result.success:
                    logger.info(f"Recognition found match with {provider_name} but confidence too low: {result.confidence:.2f}")
                    if best_result is None or result.confidence > best_result.confidence:
                        best_result = result
                
                else:
                    logger.debug(f"No match found with {provider_name}: {result.error_message}")
            
            except Exception as e:
                logger.error(f"Error with provider {provider_name}: {e}")
                continue
        
        # Clean up temporary file
        self._cleanup_audio_file(audio_file)
        
        # Return best result if any, otherwise return failure
        if best_result:
            logger.info(f"Returning best result from {best_result.provider}: {best_result.artist} - {best_result.title} (confidence: {best_result.confidence:.2f})")
            return best_result
        else:
            return RecognitionResult(
                success=False,
                confidence=0.0,
                provider='none',
                error_message="No matches found with any provider"
            )
    
    def _cleanup_audio_file(self, audio_file: str):
        """Clean up temporary audio file."""
        try:
            if audio_file and os.path.exists(audio_file) and audio_file.startswith(tempfile.gettempdir()):
                os.unlink(audio_file)
                logger.debug(f"Cleaned up audio file: {audio_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up audio file {audio_file}: {e}")
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        status = {}
        
        for provider in self.providers:
            status[provider.name] = {
                'available': provider.is_available(),
                'enabled': provider.enabled,
                'config': {
                    'timeout': provider.timeout,
                    'max_retries': provider.max_retries
                }
            }
        
        return {
            'providers': status,
            'provider_order': self.provider_order,
            'min_confidence': self.min_confidence,
            'rate_limit_delay': self.rate_limit_delay
        }
    
    def test_providers(self) -> Dict[str, Any]:
        """Test all providers and return their status."""
        results = {}
        
        for provider in self.providers:
            try:
                if provider.is_available():
                    results[provider.name] = {
                        'status': 'available',
                        'configured': True,
                        'message': f'{provider.name} is ready'
                    }
                else:
                    results[provider.name] = {
                        'status': 'unavailable', 
                        'configured': provider.enabled,
                        'message': f'{provider.name} is not properly configured'
                    }
            except Exception as e:
                results[provider.name] = {
                    'status': 'error',
                    'configured': provider.enabled,
                    'message': f'Error testing {provider.name}: {e}'
                }
        
        return results


# Convenience function for recognition
async def recognize_audio_file(audio_file: str) -> RecognitionResult:
    """
    Convenience function to recognize an audio file.
    
    Args:
        audio_file: Path to audio file
        
    Returns:
        RecognitionResult
    """
    recognizer = MusicRecognizer()
    return await recognizer.recognize_track(audio_file)