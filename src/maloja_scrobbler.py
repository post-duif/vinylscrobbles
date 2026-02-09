"""
Maloja Scrobbler

Sends recognized tracks to a Maloja server using its `/newscrobble` endpoint.
This implementation performs immediate POSTs (no shared DB queue). It's opt-in
via configuration and is designed to run alongside the Last.fm scrobbler.
"""

import aiohttp
import time
import logging
from typing import Optional, Dict, Any

from config_manager import get_config
from database import DatabaseManager, ScrobbleEntry
from music_recognizer import RecognitionResult

logger = logging.getLogger(__name__)


class MalojaScrobbler:
    """Maloja scrobbler that POSTs JSON to `/newscrobble` and queues on failure."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.config = get_config()
        self.scrobbling_config = self.config.get_scrobbling_config()
        self.maloja_config = self.scrobbling_config.get('maloja', {})

        self.database = database or DatabaseManager()

        self.enabled = self.maloja_config.get('enabled', False)
        self.api_url = self.maloja_config.get('api_url')
        self.api_key = self.maloja_config.get('api_key')
        self.timeout = self.maloja_config.get('timeout', 30)

    def is_available(self) -> bool:
        return self.enabled and bool(self.api_url)

    async def _post_scrobble(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url.rstrip('/') + '/newscrobble', json=payload, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                text = await resp.text()
                try:
                    data = await resp.json()
                except Exception:
                    data = {'status': 'error', 'desc': text}
                return {'status_code': resp.status, 'json': data}

    def scrobble_now(self, recognition_result: RecognitionResult, timestamp: Optional[int] = None) -> Dict[str, Any]:
        """Attempt to scrobble now; on failure, queue in DB for retry."""
        if not recognition_result.success or not recognition_result.artist or not recognition_result.title:
            return {'status': 'error', 'message': 'Invalid recognition result'}

        if not self.is_available():
            return {'status': 'disabled', 'message': 'Maloja scrobbling is disabled'}

        payload = {
            'artists': [recognition_result.artist],
            'title': recognition_result.title,
        }
        if recognition_result.album:
            payload['album'] = recognition_result.album
        if recognition_result.duration:
            payload['duration'] = int(recognition_result.duration)
        payload['time'] = int(timestamp or int(time.time()))

        if self.api_key:
            payload['apikey'] = self.api_key

        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._post_scrobble(payload))
            finally:
                loop.close()

            status_code = result.get('status_code')
            response = result.get('json')

            if status_code == 200 and response and response.get('status') in ('success', 'ok'):
                # Add to history
                entry = ScrobbleEntry(
                    artist=recognition_result.artist,
                    title=recognition_result.title,
                    album=recognition_result.album,
                    timestamp=payload.get('time'),
                    duration=recognition_result.duration
                )
                try:
                    self.database.add_to_history(entry, 'maloja', 1.0, metadata=response)
                except Exception:
                    logger.debug('Failed to add maloja scrobble to history')

                return {'status': 'success', 'response': response}

            else:
                # Queue for retry in DB
                entry = ScrobbleEntry(
                    artist=recognition_result.artist,
                    title=recognition_result.title,
                    album=recognition_result.album,
                    timestamp=payload.get('time'),
                    duration=recognition_result.duration
                )
                metadata = {'payload': payload, 'response': response}
                try:
                    self.database.add_to_scrobble_queue(entry, metadata)
                except Exception as e:
                    logger.error(f'Failed to queue maloja scrobble: {e}')

                return {'status': 'queued', 'response': response}

        except Exception as e:
            logger.error(f"Maloja scrobble error: {e}")
            # Queue in DB as fallback
            entry = ScrobbleEntry(
                artist=recognition_result.artist,
                title=recognition_result.title,
                album=recognition_result.album,
                timestamp=int(time.time()),
                duration=recognition_result.duration
            )
            metadata = {'payload': payload, 'error': str(e)}
            try:
                self.database.add_to_scrobble_queue(entry, metadata)
            except Exception as ex:
                logger.error(f'Failed to queue maloja scrobble after exception: {ex}')

            return {'status': 'error', 'message': str(e)}
