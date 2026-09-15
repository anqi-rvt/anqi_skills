"""Thin wrapper over the Outline REST API endpoints this pipeline uses.

Every method here mirrors a call validated live against the real Rivet
workspace (see design.md for the confirmed request/response shapes). Not
unit-tested directly — it's exercised through `sync.py --dry-run` and live
runs, the same way `render_md.py` (vendored from a sibling project) has no
test file and is validated by running it.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

import requests


class OutlineAPIError(RuntimeError):
    def __init__(self, endpoint: str, status_code: int, body: dict):
        message = body.get("message", str(body))
        super().__init__(f"{endpoint} failed ({status_code}): {message}")
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body


class OutlineClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        verify: bool | None = None,
    ):
        self.base_url = (base_url or os.environ.get("OUTLINE_URL", "https://outline.rvt")).rstrip(
            "/"
        )
        self.api_key = api_key or os.environ["OUTLINE_API_KEY"]
        # Default to real TLS verification; only skip it on explicit
        # opt-in (OUTLINE_INSECURE=1 — was needed against Rivet's internal
        # CA during development), never silently.
        self.verify = verify if verify is not None else os.environ.get("OUTLINE_INSECURE") != "1"
        if not self.verify:
            requests.packages.urllib3.disable_warnings()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def _post(self, endpoint: str, payload: dict | None = None, **kwargs: Any) -> dict:
        r = self.session.post(
            f"{self.base_url}/api/{endpoint}",
            json=payload,
            verify=self.verify,
            timeout=30,
            **kwargs,
        )
        if not r.ok:
            try:
                body = r.json()
            except ValueError:
                body = {"message": r.text}
            raise OutlineAPIError(endpoint, r.status_code, body)
        return r.json()

    # -- documents -----------------------------------------------------

    def create_document(
        self, title: str, text: str, collection_id: str, parent_document_id: str | None = None
    ) -> dict:
        payload = {"title": title, "text": text, "collectionId": collection_id, "publish": True}
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
        return self._post("documents.create", payload)["data"]

    def update_document(
        self, document_id: str, text: str | None = None, title: str | None = None
    ) -> dict:
        payload: dict[str, Any] = {"id": document_id}
        if text is not None:
            payload["text"] = text
        if title is not None:
            payload["title"] = title
        return self._post("documents.update", payload)["data"]

    def get_document(self, document_id: str) -> dict:
        return self._post("documents.info", {"id": document_id})["data"]

    def list_revisions(self, document_id: str) -> list[dict]:
        # Confirmed this session: it's `revisions.list`, not
        # `documents.revisions` (design.md's original, untested guess).
        return self._post("revisions.list", {"documentId": document_id})["data"]

    def delete_document(self, document_id: str, permanent: bool = False) -> None:
        # Confirmed this session: a member-level key can only soft-delete
        # (trash); permanent=True returns a 403 authorization_error. The
        # sync script never deletes documents anyway (never delete+recreate).
        payload: dict[str, Any] = {"id": document_id}
        if permanent:
            payload["permanent"] = True
        self._post("documents.delete", payload)

    # -- attachments -----------------------------------------------------

    def upload_attachment(self, path: Path, document_id: str) -> str:
        path = Path(path)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data = self._post(
            "attachments.create",
            {
                "name": path.name,
                "documentId": document_id,
                "contentType": content_type,
                "size": path.stat().st_size,
            },
        )["data"]
        upload_url = self.base_url + data["uploadUrl"]
        with open(path, "rb") as f:
            r = self.session.post(
                upload_url,
                data=data["form"],
                files={"file": (path.name, f, content_type)},
                verify=self.verify,
                timeout=60,
            )
        if not r.ok:
            raise OutlineAPIError("files.create", r.status_code, {"message": r.text})
        return data["attachment"]["url"]

    # -- comments -----------------------------------------------------

    def list_comments(self, document_id: str, include_anchor_text: bool = True) -> list[dict]:
        payload: dict[str, Any] = {"documentId": document_id, "limit": 100, "offset": 0}
        if include_anchor_text:
            payload["includeAnchorText"] = True
        comments: list[dict] = []
        while True:
            body = self._post("comments.list", payload)
            comments.extend(body["data"])
            total = body["pagination"]["total"]
            payload["offset"] += len(body["data"])
            if payload["offset"] >= total or not body["data"]:
                break
        return comments

    def create_comment(
        self, document_id: str, text: str, parent_comment_id: str | None = None
    ) -> dict:
        payload: dict[str, Any] = {"documentId": document_id, "text": text}
        if parent_comment_id:
            payload["parentCommentId"] = parent_comment_id
        return self._post("comments.create", payload)["data"]
