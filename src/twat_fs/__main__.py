#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "fire",
# ]
# ///
# this_file: src/twat_fs/__main__.py

"""
Command-line interface for twat-fs package.
"""

from pathlib import Path

import fire

from twat_fs.upload import (
    upload_file as _upload_file,
    ProviderType,
    PROVIDERS_PREFERENCE,
)


def upload_file(
    file_path: str | Path,
    provider: ProviderType | list[ProviderType] | None = PROVIDERS_PREFERENCE,
) -> str:
    """
    Upload a file using the specified provider.

    Args:
        file_path: Path to the file to upload
        provider: Name of the provider to use

    Returns:
        str: URL of the uploaded file
    """
    return _upload_file(file_path, provider)


def main():
    """Entry point for the CLI."""
    fire.Fire({"upload_file": upload_file})


if __name__ == "__main__":
    main()
