"""Service for communicating with YouTube Data API for video/playlist operations."""

import logging
from typing import Any

from googleapiclient.errors import HttpError

from api.youtube_client import YouTubeClient, YouTubeAPIClientError

logger = logging.getLogger(__name__)


class VideoServiceError(Exception):
    """Base exception for video service API errors."""
    pass


class UploadsPlaylistNotFoundError(VideoServiceError):
    """Raised when a channel has no uploads playlist."""
    pass


class VideoService:
    """Handles YouTube Data API communication for video and playlist lookups.

    Uses the existing YouTubeClient from Phase 1.
    """

    def __init__(self, client: YouTubeClient | None = None) -> None:
        self._client = client or YouTubeClient()

    def get_uploads_playlist_id(self, channel_id: str) -> str:
        """Retrieve the uploads playlist ID for a given channel.

        Calls ``channels.list(part="contentDetails")`` and extracts
        ``relatedPlaylists.uploads``.

        Args:
            channel_id: The YouTube channel ID (``UC...``).

        Returns:
            The uploads playlist ID (``UU...``).

        Raises:
            VideoServiceError: If the API request fails.
            UploadsPlaylistNotFoundError: If the playlist ID is missing.
        """
        service = self._client.get_service()
        logger.info("Fetching uploads playlist ID for channel %s", channel_id)

        try:
            response: dict[str, Any] = (
                service.channels()
                .list(part="contentDetails", id=channel_id)
                .execute()
            )
        except HttpError as exc:
            status = exc.resp.status
            reason = getattr(exc, "reason", str(exc))
            logger.error("YouTube API HTTP %d error: %s", status, reason)

            if status == 403:
                error_body = str(exc)
                if "quotaExceeded" in error_body or "quota" in error_body.lower():
                    raise VideoServiceError(
                        "API quota exceeded. Try again later."
                    ) from exc
                raise VideoServiceError(
                    f"API request forbidden. Check API key. Reason: {reason}"
                ) from exc
            if status == 400:
                raise VideoServiceError(
                    f"Bad request. Reason: {reason}"
                ) from exc
            if status == 404:
                raise VideoServiceError(
                    f"Channel not found: {channel_id}"
                ) from exc
            raise VideoServiceError(f"HTTP {status}: {reason}") from exc
        except YouTubeAPIClientError as exc:
            raise VideoServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error fetching playlist: %s", exc)
            raise VideoServiceError(f"Unexpected error: {exc}") from exc

        items = response.get("items", [])
        if not items:
            raise VideoServiceError(f"No channel found for ID: {channel_id}")

        uploads_id = (
            items[0]
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads_id:
            raise UploadsPlaylistNotFoundError(
                f"Channel {channel_id} has no uploads playlist."
            )

        logger.info("Uploads playlist ID: %s", uploads_id)
        return uploads_id

    def get_playlist_items(
        self,
        playlist_id: str,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a single page of playlist items from the YouTube API.

        Args:
            playlist_id: The playlist ID to fetch items from.
            page_token: Optional page token for pagination.

        Returns:
            Dict with keys:
            - ``video_ids``: List of video ID strings from this page.
            - ``next_page_token``: Token for the next page, or ``None``.
            - ``page_item_count``: Number of items on this page.

        Raises:
            VideoServiceError: If the API request fails.
        """
        service = self._client.get_service()
        page_label = f"page_token={page_token}" if page_token else "first page"
        logger.info("Requesting playlist items: playlist=%s, %s", playlist_id, page_label)

        params: dict[str, Any] = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            response: dict[str, Any] = (
                service.playlistItems()
                .list(**params)
                .execute()
            )
        except HttpError as exc:
            status = exc.resp.status
            reason = getattr(exc, "reason", str(exc))
            logger.error("YouTube API HTTP %d error: %s", status, reason)

            if status == 403:
                error_body = str(exc)
                if "quotaExceeded" in error_body or "quota" in error_body.lower():
                    raise VideoServiceError(
                        "API quota exceeded. Try again later."
                    ) from exc
                raise VideoServiceError(
                    f"API request forbidden. Check API key. Reason: {reason}"
                ) from exc
            if status == 404:
                raise VideoServiceError(
                    f"Playlist not found: {playlist_id}"
                ) from exc
            raise VideoServiceError(f"HTTP {status}: {reason}") from exc
        except YouTubeAPIClientError as exc:
            raise VideoServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error fetching playlist items: %s", exc)
            raise VideoServiceError(f"Unexpected error: {exc}") from exc

        items = response.get("items", [])
        video_ids: list[str] = []
        for item in items:
            resource_id = (
                item.get("snippet", {})
                .get("resourceId", {})
            )
            kind = resource_id.get("kind")
            v_id = resource_id.get("videoId")
            if kind == "youtube#video" and v_id:
                video_ids.append(v_id)

        next_token: str | None = response.get("nextPageToken")
        logger.info(
            "Page received: %d items, nextPageToken=%s",
            len(video_ids),
            next_token or "None",
        )

        return {
            "video_ids": video_ids,
            "next_page_token": next_token,
            "page_item_count": len(video_ids),
        }

    def get_videos_batch(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch metadata for a batch of up to 50 videos.

        Calls ``videos.list`` with ``part="snippet,contentDetails,statistics"``.

        Args:
            video_ids: List of YouTube video IDs (max 50).

        Returns:
            Raw API response items for videos that were found.
            Deleted/private/invalid IDs are silently omitted by the API.

        Raises:
            VideoServiceError: If the API request fails.
        """
        if not video_ids:
            return []

        service = self._client.get_service()
        joined = ",".join(video_ids)
        logger.info(
            "Fetching metadata batch: %d videos (ids: %s..)",
            len(video_ids),
            joined[:60],
        )

        try:
            response: dict[str, Any] = (
                service.videos()
                .list(
                    part="snippet,contentDetails,statistics",
                    id=joined,
                )
                .execute()
            )
        except HttpError as exc:
            status = exc.resp.status
            reason = getattr(exc, "reason", str(exc))
            logger.error("YouTube API HTTP %d error: %s", status, reason)

            if status == 403:
                error_body = str(exc)
                if "quotaExceeded" in error_body or "quota" in error_body.lower():
                    raise VideoServiceError(
                        "API quota exceeded. Try again later."
                    ) from exc
                raise VideoServiceError(
                    f"API request forbidden. Check API key. Reason: {reason}"
                ) from exc
            if status == 400:
                raise VideoServiceError(
                    f"Bad request. Reason: {reason}"
                ) from exc
            raise VideoServiceError(f"HTTP {status}: {reason}") from exc
        except YouTubeAPIClientError as exc:
            raise VideoServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("Unexpected error fetching video batch: %s", exc)
            raise VideoServiceError(f"Unexpected error: {exc}") from exc

        items: list[dict[str, Any]] = response.get("items", [])
        logger.info("Batch response: %d items of %d requested", len(items), len(video_ids))
        return items
