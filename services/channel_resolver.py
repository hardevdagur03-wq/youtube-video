"""Business logic for validating and resolving YouTube channel handles."""

import logging
import re

from api.channel_service import (
    ChannelService,
    ChannelNotFoundError,
    ChannelServiceError,
)

logger = logging.getLogger(__name__)

HANDLE_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,30}$")


class ChannelResolverError(Exception):
    """Base exception for channel resolution errors."""
    pass


class InvalidHandleError(ChannelResolverError):
    """Raised when the provided handle fails format validation."""
    pass


class ChannelResolver:
    """Orchestrates handle validation and channel ID resolution.

    Separates concerns:
    - Input validation (static method)
    - API orchestration (resolve method)
    """

    def __init__(self, channel_service: ChannelService | None = None) -> None:
        self._channel_service = channel_service or ChannelService()

    @staticmethod
    def validate_handle(handle: str) -> str:
        """Validate and normalize a YouTube channel handle.

        Rules:
        - Must not be empty or whitespace-only.
        - Must be 3–30 characters (after stripping ``@``).
        - May contain letters, digits, dots, hyphens, and underscores.

        Args:
            handle: Raw input string.

        Returns:
            Normalized handle with ``@`` prefix.

        Raises:
            InvalidHandleError: If validation fails.
        """
        cleaned = handle.strip()
        if not cleaned:
            raise InvalidHandleError("Channel handle cannot be empty.")

        stripped = cleaned.lstrip("@")
        if not HANDLE_PATTERN.match(stripped):
            raise InvalidHandleError(
                f"Invalid channel handle: '{handle}'. "
                "A handle must be 3–30 characters and may contain letters, "
                "digits, dots, hyphens, or underscores."
            )
        return f"@{stripped}"

    def resolve(self, raw_handle: str) -> dict:
        """Full resolution pipeline: validate → API call → parse response.

        Args:
            raw_handle: User-provided channel handle (e.g. ``@channel`` or ``channel``).

        Returns:
            Dictionary with keys:
            - ``channel_id``: Resolved YouTube channel ID.
            - ``title``: Channel display name.
            - ``handle``: Normalized handle (with ``@``).

        Raises:
            InvalidHandleError: If input format is invalid.
            ChannelResolverError: If API resolution fails.
        """
        logger.info("Channel lookup started for input: %s", raw_handle)

        normalized = self.validate_handle(raw_handle)
        logger.info("Input validated, normalized handle: %s", normalized)

        try:
            item = self._channel_service.resolve_handle(normalized)
        except ChannelNotFoundError as exc:
            logger.error("Channel not found: %s", exc)
            raise ChannelResolverError(str(exc)) from exc
        except ChannelServiceError as exc:
            logger.error("Channel service error: %s", exc)
            raise ChannelResolverError(str(exc)) from exc

        channel_id = item["id"]
        title = item.get("snippet", {}).get("title", "Unknown")

        logger.info(
            "Channel resolved: ID=%s, Title='%s'",
            channel_id,
            title,
        )

        return {
            "channel_id": channel_id,
            "title": title,
            "handle": normalized,
        }
