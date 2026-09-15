from __future__ import annotations

import json

import pytest

from manifest import Manifest, sha256_file


class FakeClient:
    """Records upload calls; returns a deterministic fake URL per call."""

    def __init__(self):
        self.calls = []

    def upload_attachment(self, path, document_id):
        self.calls.append((str(path), document_id))
        return f"/api/attachments.redirect?id=fake-{len(self.calls)}"


def test_sha256_file_is_stable(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    assert sha256_file(f) == sha256_file(f)
    assert len(sha256_file(f)) == 64


def test_sha256_file_differs_on_content_change(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello")
    digest1 = sha256_file(f)
    f.write_bytes(b"world")
    digest2 = sha256_file(f)
    assert digest1 != digest2


def test_resolve_uploads_once_for_new_file(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    client = FakeClient()
    m = Manifest()

    url = m.resolve(f, client, "doc-1")

    assert url == "/api/attachments.redirect?id=fake-1"
    assert len(client.calls) == 1


def test_resolve_skips_upload_when_hash_known(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    client = FakeClient()
    m = Manifest()

    url1 = m.resolve(f, client, "doc-1")
    url2 = m.resolve(f, client, "doc-1")

    assert url1 == url2
    assert len(client.calls) == 1  # not re-uploaded


def test_resolve_reuploads_when_content_changes(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello")
    client = FakeClient()
    m = Manifest()
    m.resolve(f, client, "doc-1")

    f.write_bytes(b"world")
    m.resolve(f, client, "doc-1")

    assert len(client.calls) == 2


def test_resolve_dedupes_by_hash_across_different_paths(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"same bytes")
    b.write_bytes(b"same bytes")
    client = FakeClient()
    m = Manifest()

    url_a = m.resolve(a, client, "doc-1")
    url_b = m.resolve(b, client, "doc-1")

    assert url_a == url_b
    assert len(client.calls) == 1


def test_save_and_load_round_trip(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    client = FakeClient()
    m = Manifest()
    m.resolve(f, client, "doc-1")

    manifest_path = tmp_path / "manifest.json"
    m.save(manifest_path)

    reloaded = Manifest.load(manifest_path)
    # no new upload needed; hash already known from disk
    url = reloaded.resolve(f, client, "doc-1")
    assert len(client.calls) == 1
    assert url == "/api/attachments.redirect?id=fake-1"


def test_load_missing_file_returns_empty_manifest(tmp_path):
    m = Manifest.load(tmp_path / "does-not-exist.json")
    assert m.entries == {}


def test_saved_file_is_readable_json(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    m = Manifest()
    m.resolve(f, FakeClient(), "doc-1")
    manifest_path = tmp_path / "manifest.json"
    m.save(manifest_path)

    with open(manifest_path, encoding="utf-8") as fh:
        data = json.load(fh)
    digest = sha256_file(f)
    assert digest in data
    assert data[digest]["url"] == "/api/attachments.redirect?id=fake-1"
    assert data[digest]["source_path"] == str(f).replace("\\", "/")
    assert "uploaded_at" in data[digest]


def test_save_does_not_corrupt_existing_file_on_failure(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"already": "here"}', encoding="utf-8")

    m = Manifest({"new": {"url": "x"}})

    def boom(*a, **k):
        raise OSError("simulated write failure")

    monkeypatch.setattr("manifest.json.dump", boom)
    with pytest.raises(OSError):
        m.save(manifest_path)

    # save() must write to a temp file and swap it in atomically, so a
    # failure partway through must never truncate/corrupt the existing file.
    with open(manifest_path, encoding="utf-8") as fh:
        assert json.load(fh) == {"already": "here"}
    # no leftover temp file
    assert list(tmp_path.glob("manifest.json.*.tmp")) == []


def test_save_leaves_no_temp_file_on_success(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"hello world")
    m = Manifest()
    m.resolve(f, FakeClient(), "doc-1")
    manifest_path = tmp_path / "manifest.json"
    m.save(manifest_path)

    assert {p.name for p in tmp_path.iterdir()} == {"a.png", "manifest.json"}
