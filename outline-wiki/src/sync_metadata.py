"""Per-document sync bookkeeping, consolidated into one JSON file per
`.qmd` (`<name>.outline-wiki-metadata.json`) instead of three separate
sidecar files (a markdown cache plus two snapshot JSON files).

This holds state specific to one document: the body as of the last
successful sync (for the manual-edit reconciliation diff), and the
comment/revision snapshots taken immediately before the most recent push.
It is deliberately separate from the attachment manifest (`manifest.py`),
which can be shared across multiple documents for cross-page dedup and so
does not belong inside a single document's metadata file.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


class SyncMetadata:
    def __init__(
        self,
        last_synced_body: str = "",
        comments_snapshot: list | None = None,
        revisions_snapshot: list | None = None,
    ):
        self.last_synced_body = last_synced_body
        self.comments_snapshot = comments_snapshot or []
        self.revisions_snapshot = revisions_snapshot or []

    @staticmethod
    def path_for(qmd_path: Path) -> Path:
        return Path(qmd_path).with_suffix(".outline-wiki-metadata.json")

    @classmethod
    def load(cls, path: Path) -> SyncMetadata:
        if not Path(path).exists():
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            last_synced_body=data.get("last_synced_body", ""),
            comments_snapshot=data.get("comments_snapshot", []),
            revisions_snapshot=data.get("revisions_snapshot", []),
        )

    def save(self, path: Path) -> None:
        """Write atomically: a crash/interrupt mid-write must never leave
        `path` truncated or corrupted."""
        path = Path(path)
        tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        data = {
            "last_synced_body": self.last_synced_body,
            "comments_snapshot": self.comments_snapshot,
            "revisions_snapshot": self.revisions_snapshot,
        }
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)
