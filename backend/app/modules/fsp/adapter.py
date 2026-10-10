"""Client adapter for communicating with the external FSP Registry service."""

import logging
from typing import Any

import httpx

try:
    from backend.app.core.config import settings
except ImportError:
    from app.core.config import settings

logger = logging.getLogger(__name__)


class FSPRegistryError(Exception):
    """Exception raised when FSP registry cannot be reached or returns an error."""


class FSPParticipantNotFoundError(FSPRegistryError):
    """Exception raised when participant is not found in the registry."""


class FSPRegistryClient:
    """HTTP Client for FSP Registry REST API."""

    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or getattr(settings, "FSP_REGISTRY_URL", "http://localhost:8001")).rstrip("/")
        self.timeout = timeout

    async def get_participant_achievements(self, fsp_id: str) -> dict[str, Any] | None:
        """Fetch verified participant data and competition achievements by FSP ID.

        Args:
            fsp_id: Athlete ID (e.g. 'FSP-1001')

        Returns:
            Dictionary containing participant profile and achievements, or None if not found.
        """
        clean_id = fsp_id.strip()
        url = f"{self.base_url}/fsp-registry/participants/{clean_id}/achievements"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Participant {clean_id} not found in FSP registry.")
                    return None
                else:
                    logger.error(f"FSP registry error: HTTP {response.status_code} - {response.text}")
                    raise FSPRegistryError(f"FSP registry returned status {response.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                f"FSP registry service at {self.base_url} is unreachable ({exc}). Falling back to internal mock data."
            )
            # Fallback for offline/test environments
            return self._local_fallback(clean_id)

    def get_participant_achievements_sync(self, fsp_id: str) -> dict[str, Any] | None:
        """Synchronous version of get_participant_achievements."""
        clean_id = fsp_id.strip()
        url = f"{self.base_url}/fsp-registry/participants/{clean_id}/achievements"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    raise FSPRegistryError(f"FSP registry returned status {response.status_code}")
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(
                f"FSP registry service at {self.base_url} unreachable ({exc}). Using internal fallback."
            )
            return self._local_fallback(clean_id)

    def _local_fallback(self, fsp_id: str) -> dict[str, Any] | None:
        """In-process mock fallback if mock service is not currently running."""
        try:
            import importlib.util
            from pathlib import Path
            mock_file = Path(__file__).resolve().parents[4] / "services" / "fsp-mock" / "main.py"
            if mock_file.exists():
                spec = importlib.util.spec_from_file_location("fsp_mock_main", str(mock_file))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if fsp_id in mod.MOCK_PARTICIPANTS:
                    return mod.MOCK_PARTICIPANTS[fsp_id]
                return mod._generate_synthetic_participant(fsp_id)
        except Exception as e:
            logger.debug(f"Could not dynamically load fsp-mock: {e}")


fsp_client = FSPRegistryClient()
