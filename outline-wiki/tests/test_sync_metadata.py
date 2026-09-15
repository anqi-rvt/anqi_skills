from __future__ import annotations

import contextlib
import json

from sync_metadata import SyncMetadata


def test_path_for_derives_from_qmd_filename(tmp_path):
    qmd = tmp_path / "sample.qmd"
    assert SyncMetadata.path_for(qmd) == tmp_path / "sample.outline-wiki-metadata.json"


def test_load_missing_file_returns_empty_defaults(tmp_path):
    m = SyncMetadata.load(tmp_path / "does-not-exist.json")
    assert m.last_synced_body == ""
    assert m.comments_snapshot == []
    assert m.revisions_snapshot == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "sample.outline-wiki-metadata.json"
    m = SyncMetadata(
        last_synced_body="# Title\n\nBody.\n",
        comments_snapshot=[{"id": "c1", "anchorText": "foo"}],
        revisions_snapshot=[{"id": "r1"}],
    )
    m.save(path)

    reloaded = SyncMetadata.load(path)
    assert reloaded.last_synced_body == "# Title\n\nBody.\n"
    assert reloaded.comments_snapshot == [{"id": "c1", "anchorText": "foo"}]
    assert reloaded.revisions_snapshot == [{"id": "r1"}]


def test_save_writes_one_readable_json_file(tmp_path):
    path = tmp_path / "sample.outline-wiki-metadata.json"
    SyncMetadata(last_synced_body="x").save(path)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["last_synced_body"] == "x"
    assert data["comments_snapshot"] == []
    assert data["revisions_snapshot"] == []


def test_save_does_not_corrupt_existing_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "sample.outline-wiki-metadata.json"
    path.write_text('{"already": "here"}', encoding="utf-8")

    def boom(*a, **k):
        raise OSError("simulated write failure")

    monkeypatch.setattr("sync_metadata.json.dump", boom)
    m = SyncMetadata(last_synced_body="new")
    with contextlib.suppress(OSError):
        m.save(path)

    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"already": "here"}
    assert list(tmp_path.glob("*.tmp")) == []
