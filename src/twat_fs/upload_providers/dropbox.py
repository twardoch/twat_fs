#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "dropbox",
#   "python-dotenv",
#   "tenacity",
#   "loguru",
# ]
# ///
# this_file: src/twat_fs/upload_providers/dropbox.py

"""
Dropbox provider for file uploads.
This module provides functionality to upload files to Dropbox and get shareable links.
Supports optional force and unique upload modes, chunked uploads for large files, and custom upload paths.
"""

import os
from urllib import parse

from pathlib import Path
from datetime import datetime

import dropbox
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger


load_dotenv()

# Constants
DEFAULT_UPLOAD_PATH = "/upload"
MAX_FILE_SIZE = 150 * 1024 * 1024  # 150MB
SMALL_FILE_THRESHOLD = 4 * 1024 * 1024  # 4MB threshold for chunked upload


class DropboxUploadError(Exception):
    """Base class for Dropbox upload errors."""


class PathConflictError(DropboxUploadError):
    """Raised when a path conflict occurs in safe mode."""


class FileExistsError(PathConflictError):
    """Raised when target file already exists in safe mode."""


class FolderExistsError(PathConflictError):
    """Raised when target path is a folder in safe mode."""


def provider_auth() -> bool:
    """
    Check if Dropbox provider is properly authenticated.

    Returns:
        bool: True if DROPBOX_APP_TOKEN environment variable is set, False otherwise
    """
    has_token = bool(os.getenv("DROPBOX_APP_TOKEN"))
    if not has_token:
        logger.warning("DROPBOX_APP_TOKEN environment variable is not set")
    return has_token


def _validate_file(local_path: Path) -> None:
    """Validate file exists and size is within limits."""
    if not local_path.exists() or not local_path.is_file():
        msg = f"File not found: {local_path}"
        raise FileNotFoundError(msg)

    size = local_path.stat().st_size
    if size > MAX_FILE_SIZE:
        msg = f"File too large: {size / 1024 / 1024:.1f}MB > {MAX_FILE_SIZE / 1024 / 1024:.1f}MB"
        raise ValueError(msg)


def _get_download_url(url: str) -> str | None:
    """Convert a Dropbox share URL to a direct download URL."""
    if not url:
        return None
    parsed = parse.urlparse(url)
    query = dict(parse.parse_qsl(parsed.query))
    query["dl"] = "1"
    return parsed._replace(query=parse.urlencode(query)).geturl()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def _get_share_url(dbx: dropbox.Dropbox, db_path: str) -> str | None:
    """Get a shareable link for the uploaded file, reusing existing if possible."""
    try:
        shared_link = dbx.sharing_create_shared_link_with_settings(db_path)
        url = shared_link.url
    except dropbox.exceptions.ApiError as e:
        if "shared_link_already_exists" in str(e):
            existing_links = dbx.sharing_list_shared_links(db_path).links
            if existing_links:
                url = existing_links[0].url
            else:
                msg = f"Failed to get existing share link: {e}"
                raise DropboxUploadError(msg)
        else:
            msg = f"Failed to create share link: {e}"
            raise DropboxUploadError(msg) from e

    return _get_download_url(url) if url else None


def _ensure_upload_directory(dbx: dropbox.Dropbox, upload_path: str) -> None:
    """Ensure target upload directory exists and is a folder."""
    try:
        meta = dbx.files_get_metadata(upload_path)
        if isinstance(meta, dropbox.files.FolderMetadata):
            return
        # Path exists but isn't a folder - delete and recreate
        dbx.files_delete_v2(upload_path)
        dbx.files_create_folder_v2(upload_path)
    except dropbox.exceptions.ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            dbx.files_create_folder_v2(upload_path)
        else:
            msg = f"Directory validation failed: {e}"
            raise DropboxUploadError(msg) from e


def upload_file(
    file_path: str | Path,
    force: bool = False,
    unique: bool = False,
    upload_path: str = DEFAULT_UPLOAD_PATH,
) -> str:
    """
    Upload a file to Dropbox and return its shareable URL.

    Args:
        file_path: Path to the file to upload (str or Path)
        force: If True, overwrite an existing file (default: False). If False and the file exists, the upload is skipped.
        unique: If True, append a timestamp to the filename to ensure uniqueness (default: False).
        upload_path: Dropbox folder to upload the file into (default: /upload).

    Returns:
        str: URL of the uploaded file

    Raises:
        DropboxUploadError: If the upload or share link creation fails.
        ValueError: If the file is too large or token is missing.
    """
    if not provider_auth():
        msg = "DROPBOX_APP_TOKEN environment variable must be set"
        raise ValueError(msg)

    path = Path(file_path)
    _validate_file(path)

    # Determine the target filename based on unique mode
    if unique:
        timestamp = datetime.now().strftime("%y%m%d%H%M%S")
        filename = f"{path.stem}-{timestamp}{path.suffix}"
    else:
        filename = path.name

    # Construct the target Dropbox path (normalize to not have trailing '/')
    target_path = f"{upload_path.rstrip('/')}/{filename}"
    token = os.getenv("DROPBOX_APP_TOKEN")
    dbx = dropbox.Dropbox(token)

    # Add directory validation before upload
    _ensure_upload_directory(dbx, upload_path.rstrip("/"))

    # Enhanced existing file check
    if not unique:
        try:
            meta = dbx.files_get_metadata(target_path)
            if isinstance(meta, dropbox.files.FolderMetadata):
                msg = f"Path {target_path} is a directory"
                raise FolderExistsError(msg)

            logger.info(f"File exists at {target_path}")
            if not force:
                return _get_share_url(dbx, target_path)

        except dropbox.exceptions.ApiError as e:
            if not (e.error.is_path() and e.error.get_path().is_not_found()):
                raise

    file_size = path.stat().st_size
    mode = dropbox.files.WriteMode.overwrite if force else dropbox.files.WriteMode.add

    try:
        with open(path, "rb") as f:
            if file_size <= SMALL_FILE_THRESHOLD:
                # Small file upload in one request
                content = f.read()
                logger.info(
                    f"Uploading small file: {path} ({file_size} bytes) to {target_path}"
                )
                dbx.files_upload(content, target_path, mode=mode)
            else:
                # Chunked upload for large files with progress tracking
                logger.info(
                    f"Uploading large file: {path} ({file_size} bytes) to {target_path} in chunks"
                )
                chunk_size = SMALL_FILE_THRESHOLD
                initial_chunk = f.read(chunk_size)
                session = dbx.files_upload_session_start(initial_chunk)
                cursor = dropbox.files.UploadSessionCursor(
                    session_id=session.session_id, offset=f.tell()
                )
                commit = dropbox.files.CommitInfo(path=target_path, mode=mode)
                last_progress = 0
                while f.tell() < file_size:
                    is_last_chunk = (file_size - f.tell()) <= chunk_size
                    chunk = f.read(chunk_size)
                    if is_last_chunk:
                        dbx.files_upload_session_finish(chunk, cursor, commit)
                    else:
                        dbx.files_upload_session_append_v2(chunk, cursor)
                        cursor.offset = f.tell()
                    progress = int((f.tell() / file_size) * 100)
                    if progress >= last_progress + 10:
                        logger.info(f"Upload progress: {progress}%")
                        last_progress = progress
        url = _get_share_url(dbx, target_path)
        if not url:
            msg = "Failed to get share URL"
            raise DropboxUploadError(msg)
        return url

    except Exception as e:
        msg = f"Upload failed: {e}"
        raise DropboxUploadError(msg)
