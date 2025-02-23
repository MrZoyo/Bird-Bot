# bot/utils/media_handler.py
import aiohttp
import os
import hashlib
import logging
from typing import Optional, Tuple


class MediaHandler:
    def __init__(self, archive_path: str, size_limit: int):
        self.archive_path = archive_path
        self.size_limit = size_limit  # in bytes
        self.media_folder = "media"

    async def check_file_size(self, url: str) -> Optional[int]:
        """Check file size before downloading."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url) as response:
                    if response.status == 200:
                        return int(response.headers.get('content-length', 0))
        except Exception as e:
            logging.error(f"Error checking file size: {e}")
        return None

    def get_file_path(self, url: str, ticket_id: str) -> Tuple[str, str]:
        """Generate unique file path for media."""
        # Create hash from URL to ensure unique filenames
        file_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        original_name = os.path.basename(url.split('?')[0])  # Remove query parameters
        filename = f"{file_hash}_{original_name}"

        # Create media directory if it doesn't exist
        media_dir = os.path.join(self.archive_path, ticket_id, self.media_folder)
        os.makedirs(media_dir, exist_ok=True)

        return os.path.join(media_dir, filename), filename

    async def download_media(self, url: str, ticket_id: str) -> Optional[dict]:
        """
        Download media file if within size limit.
        Returns dict with original_url, local_path, and size if successful.
        """
        try:
            file_size = await self.check_file_size(url)

            if file_size is None or file_size > self.size_limit:
                return {
                    "original_url": url,
                    "local_path": None,
                    "size": file_size,
                    "downloaded": False
                }

            file_path, filename = self.get_file_path(url, ticket_id)

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)

                        return {
                            "original_url": url,
                            "local_path": os.path.join(self.media_folder, filename),
                            "size": file_size,
                            "downloaded": True
                        }

        except Exception as e:
            logging.error(f"Error downloading media from {url}: {e}")

        return None