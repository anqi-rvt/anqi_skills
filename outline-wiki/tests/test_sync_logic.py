from __future__ import annotations

from pathlib import Path

from sync import find_local_asset_refs, normalize_table_whitespace, rewrite_asset_links, texts_match


def test_normalize_table_whitespace_collapses_separator_padding():
    a = "| Label | Preview |\n|---|---|\n| Target | x |\n"
    b = "| Label | Preview |\n|-------|---------|\n| Target | x |\n"
    assert normalize_table_whitespace(a) == normalize_table_whitespace(b)


def test_normalize_table_whitespace_collapses_cell_padding():
    a = "| Target | ![img](url) |\n"
    b = "| Target |  ![img](url) |\n"
    assert normalize_table_whitespace(a) == normalize_table_whitespace(b)


def test_normalize_table_whitespace_reproduces_confirmed_outline_diff():
    pushed = (
        "| Label | Preview |\n"
        "|---|---|\n"
        "| Target | ![cell image](/api/x) |\n"
        "| Icon | ![cell icon](/api/y) |\n"
    )
    fetched = (
        "| Label | Preview |\n"
        "|-------|---------|\n"
        "| Target |  ![cell image](/api/x) |\n"
        "| Icon  |  ![cell icon](/api/y) |\n"
    )
    assert texts_match(pushed, fetched)


def test_normalize_table_whitespace_leaves_non_table_lines_alone():
    text = "# Heading\n\nSome *prose* with no tables.\n"
    assert normalize_table_whitespace(text) == text


def test_texts_match_detects_real_content_difference():
    a = "# Title\n\nOriginal sentence.\n"
    b = "# Title\n\nEdited sentence.\n"
    assert not texts_match(a, b)


def test_rewrite_asset_links_replaces_known_local_paths():
    md = "![a](assets/x.png) and ![b](assets/y.gif)"
    url_map = {
        "assets/x.png": "/api/attachments.redirect?id=1",
        "assets/y.gif": "/api/attachments.redirect?id=2",
    }
    out = rewrite_asset_links(md, url_map)
    assert out == "![a](/api/attachments.redirect?id=1) and ![b](/api/attachments.redirect?id=2)"


def test_rewrite_asset_links_ignores_unmapped_refs():
    md = "![a](assets/unmapped.png)"
    assert rewrite_asset_links(md, {}) == md


def test_find_local_asset_refs_finds_existing_relative_files(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x.png").write_bytes(b"data")
    md = "![a](assets/x.png) and a [link](https://example.com) and ![missing](assets/missing.png)"
    refs = find_local_asset_refs(md, base_dir=tmp_path)
    assert refs == [tmp_path / "assets" / "x.png"]


def test_find_local_asset_refs_ignores_already_resolved_attachment_urls(tmp_path):
    md = "![a](/api/attachments.redirect?id=abc)"
    assert find_local_asset_refs(md, base_dir=tmp_path) == []


def test_find_local_asset_refs_rejects_traversal_outside_base_dir(tmp_path):
    # A malicious/malformed .qmd referencing a file outside the project
    # (e.g. ../../.ssh/id_rsa) must never be picked up for upload, even if
    # such a file happens to exist on disk.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside_secret = tmp_path / "secret.txt"
    outside_secret.write_bytes(b"do not upload me")
    md = "![leak](../secret.txt)"
    assert find_local_asset_refs(md, base_dir=project_dir) == []


def test_find_local_asset_refs_rejects_absolute_path_outside_base_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    outside_secret = tmp_path / "secret.txt"
    outside_secret.write_bytes(b"do not upload me")
    md = f"![leak]({outside_secret})"
    assert find_local_asset_refs(md, base_dir=project_dir) == []


def test_find_local_asset_refs_allows_relative_path_within_base_dir(tmp_path):
    (tmp_path / "assets" / "nested").mkdir(parents=True)
    (tmp_path / "assets" / "nested" / "x.png").write_bytes(b"data")
    md = "![a](assets/nested/x.png)"
    assert find_local_asset_refs(md, base_dir=tmp_path) == [
        tmp_path / "assets" / "nested" / "x.png"
    ]


def test_find_local_asset_refs_returned_paths_stay_relative_to_unresolved_base_dir(
    tmp_path, monkeypatch
):
    # Regression: find_local_asset_refs resolves base_dir internally (for
    # the traversal check), so its return value must still support
    # `path.relative_to(base_dir)` even when the caller passed an
    # unresolved/relative base_dir (e.g. sync.py calling it with
    # qmd_path.parent, a relative "example" path from the CWD) — a mismatch
    # here raises ValueError at sync time.
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x.png").write_bytes(b"data")
    monkeypatch.chdir(tmp_path)
    relative_base_dir = Path("assets").parent  # "." — deliberately unresolved
    md = "![a](assets/x.png)"
    refs = find_local_asset_refs(md, base_dir=relative_base_dir)
    assert len(refs) == 1
    # must not raise
    refs[0].relative_to(relative_base_dir.resolve())


def test_find_local_asset_refs_finds_plain_hyperlinks_too(tmp_path):
    # Video fallback deliberately uses a plain [text](path) link, not an
    # image embed — a local reference here must still get uploaded, or it
    # gets pushed as a literal relative path (which renders as a broken
    # "https://assets/..." URL).
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "x.mp4").write_bytes(b"data")
    md = "[Download video](assets/x.mp4)"
    assert find_local_asset_refs(md, base_dir=tmp_path) == [tmp_path / "assets" / "x.mp4"]


def test_rewrite_asset_links_replaces_plain_hyperlinks_too():
    md = "[Download video](assets/x.mp4)"
    out = rewrite_asset_links(md, {"assets/x.mp4": "/api/attachments.redirect?id=1"})
    assert out == "[Download video](/api/attachments.redirect?id=1)"
