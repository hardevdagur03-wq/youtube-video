import logging
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from config.settings import settings

logger = logging.getLogger(__name__)

class YouTubeAPIClientError(Exception):
    """Base exception for YouTube API Client errors."""
    pass

class YouTubeClient:
    """Authenticated client for interacting with the YouTube Data API v3."""

    def __init__(self, api_key: str = settings.youtube_api_key) -> None:
        self._api_key = api_key
        self._service: Resource | None = None

    def get_service(self) -> Resource:
        """Builds and returns the authenticated YouTube Data API v3 service resource.
        
        Uses lazy-loading to build the service only when required.
        
        Returns:
            Resource: The Google API client Resource object for YouTube API.
            
        Raises:
            YouTubeAPIClientError: If building the service fails due to configuration or network issues.
        """
        if self._service is not None:
            return self._service

        try:
            logger.info("Initializing YouTube Data API client...")
            self._service = build("youtube", "v3", developerKey=self._api_key)
            logger.info("YouTube Data API client successfully built.")
            return self._service
        except HttpError as e:
            logger.error(f"HTTP error occurred while creating YouTube client: {e}")
            raise YouTubeAPIClientError(f"HTTP error during client initialization: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error occurred during YouTube client setup: {e}")
            raise YouTubeAPIClientError(f"Failed to setup YouTube client: {e}") from e
