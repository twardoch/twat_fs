# this_file: src/twat_fs/upload_providers/protocols.py

"""
Protocol definitions for upload providers.
"""

from typing import Any, ClassVar, Protocol, TypedDict, runtime_checkable
from pathlib import Path

from twat_fs.upload_providers.types import UploadResult


class ProviderHelp(TypedDict):
    """Type for provider help messages."""

    setup: str
    deps: str


@runtime_checkable
class ProviderClient(Protocol):
    """Protocol defining the interface for upload providers."""

    provider_name: str

    def upload_file(
        self,
        local_path: str | Path,
        remote_path: str | Path | None = None,
        *,
        unique: bool = False,
        force: bool = False,
        upload_path: str | None = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Upload a file and return its public URL."""
        ...

    async def async_upload_file(
        self,
        file_path: str | Path,
        remote_path: str | Path | None = None,
        *,
        unique: bool = False,
        force: bool = False,
        upload_path: str | None = None,
        **kwargs: Any,
    ) -> UploadResult:
        """Asynchronously upload a file and return its result with timing metrics."""
        ...


@runtime_checkable
class Provider(Protocol):
    """Protocol defining what a provider module must implement."""

    PROVIDER_HELP: ClassVar[ProviderHelp]
    provider_name: str

    @classmethod
    def get_credentials(cls) -> Any | None:
        """
        Get provider credentials from environment.

        Returns:
            Optional[Any]: Provider-specific credentials or None if not configured
        """
        ...

    @classmethod
    def get_provider(cls) -> ProviderClient | None:
        """
        Initialize and return the provider client.

        Returns:
            Optional[ProviderClient]: Provider client if successful, None otherwise
        """
        ...

    def upload_file(
        self,
        local_path: str | Path,
        remote_path: str | Path | None = None,
        *,
        unique: bool = False,
        force: bool = False,
        upload_path: str | None = None,
        **kwargs: Any,
    ) -> UploadResult:
        """
        Upload a file using this provider.

        Args:
            local_path: Path to the file to upload
            remote_path: Optional remote path to use
            unique: If True, ensures unique filename
            force: If True, overwrites existing file
            upload_path: Custom upload path
            **kwargs: Additional provider-specific arguments

        Returns:
            UploadResult: Upload result with URL and timing metrics

        Raises:
            ValueError: If upload fails
        """
        ...

    async def async_upload_file(
        self,
        file_path: str | Path,
        remote_path: str | Path | None = None,
        *,
        unique: bool = False,
        force: bool = False,
        upload_path: str | None = None,
        **kwargs: Any,
    ) -> UploadResult:
        """
        Asynchronously upload a file using this provider.

        Args:
            file_path: Path to the file to upload
            remote_path: Optional remote path to use
            unique: If True, ensures unique filename
            force: If True, overwrites existing file
            upload_path: Custom upload path
            **kwargs: Additional provider-specific arguments

        Returns:
            UploadResult: Upload result with URL and timing metrics

        Raises:
            FileNotFoundError: If the file doesn't exist
            RetryableError: For temporary failures that can be retried
            NonRetryableError: For permanent failures
        """
        ...
