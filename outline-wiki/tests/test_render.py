from __future__ import annotations

from render import extract_gfm, read_front_matter, write_front_matter_field


def test_read_front_matter_parses_yaml_block(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text(
        "---\ntitle: Sample — Test Fixture\noutline_collection_id: abc-123\n---\n\n# Body\n",
        encoding="utf-8",
    )
    fm = read_front_matter(qmd)
    assert fm["title"] == "Sample — Test Fixture"
    assert fm["outline_collection_id"] == "abc-123"


def test_read_front_matter_returns_empty_dict_when_absent(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("# Just a body\n", encoding="utf-8")
    assert read_front_matter(qmd) == {}


def test_extract_gfm_title_from_front_matter(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("---\ntitle: My Title\n---\n\n# Heading\n\nBody text.\n", encoding="utf-8")
    title, body = extract_gfm(qmd)
    assert title == "My Title"
    assert "# Heading" in body
    assert "---" not in body


def test_extract_gfm_title_falls_back_to_first_h1(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("# The Real Title\n\nBody text.\n", encoding="utf-8")
    title, body = extract_gfm(qmd)
    assert title == "The Real Title"


def test_extract_gfm_title_falls_back_to_filename(tmp_path):
    qmd = tmp_path / "my_doc.qmd"
    qmd.write_text("No heading here, just text.\n", encoding="utf-8")
    title, _ = extract_gfm(qmd)
    assert title == "my_doc"


def test_extract_gfm_preserves_mermaid_fences_literally(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text(
        "# Title\n\n```mermaid\nflowchart LR\n    A --> B\n```\n",
        encoding="utf-8",
    )
    _, body = extract_gfm(qmd)
    assert "```mermaid\nflowchart LR\n    A --> B\n```" in body


def test_write_front_matter_field_updates_existing_key(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("---\ntitle: T\noutline_id: old-id\n---\n\nBody.\n", encoding="utf-8")
    write_front_matter_field(qmd, "outline_id", "new-id")
    fm = read_front_matter(qmd)
    assert fm["outline_id"] == "new-id"
    assert fm["title"] == "T"  # untouched
    assert "Body." in qmd.read_text(encoding="utf-8")


def test_write_front_matter_field_inserts_new_key(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("---\ntitle: T\n---\n\nBody.\n", encoding="utf-8")
    write_front_matter_field(qmd, "outline_id", "brand-new")
    fm = read_front_matter(qmd)
    assert fm["outline_id"] == "brand-new"
    assert fm["title"] == "T"


def test_write_front_matter_field_creates_front_matter_when_absent(tmp_path):
    qmd = tmp_path / "doc.qmd"
    qmd.write_text("# No front matter\n\nBody.\n", encoding="utf-8")
    write_front_matter_field(qmd, "outline_id", "brand-new")
    fm = read_front_matter(qmd)
    assert fm["outline_id"] == "brand-new"
    assert "# No front matter" in qmd.read_text(encoding="utf-8")
