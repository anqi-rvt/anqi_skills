"""Attachment dedup manifest (design.md: "Attachment upload and deduplication").

Outline's `attachments.create` has no content-hash/dedup field, so this
manifest lives in the pipeline: a JSON file keyed by `sha256(file bytes)`,
mapping to the resolved Outline attachment URL. Keying by hash rather than
by file path means renaming or moving a source image doesn't trigger a
spurious re-upload.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


class AttachmentUploader(Protocol):
    def upload_attachment(self, path: Path, document_id: str) -> str: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Manifest:
    def __init__(self, entries: dict[str, dict] | None = None):
        self.entries: dict[str, dict] = entries or {}

    @classmethod
    def load(cls, path: Path) -> Manifest:
        if not Path(path).exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def save(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, sort_keys=True)

    def resolve(self, file_path: Path, client: AttachmentUploader, document_id: str) -> str:
        """Return the Outline attachment URL for `file_path`, uploading only
        if its content hash isn't already recorded."""
        digest = sha256_file(file_path)
        if digest in self.entries:
            return self.entries[digest]["url"]

        url = client.upload_attachment(file_path, document_id)
        self.entries[digest] = {
            "url": url,
            "source_path": str(file_path),
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
        return url
