from __future__ import annotations

from anchors import rewrite_self_links, slugify


def test_slugify_single_word():
    assert slugify("Tables") == "h-tables"


def test_slugify_two_words():
    assert slugify("Text formatting") == "h-text-formatting"


def test_slugify_collapses_repeated_whitespace():
    assert slugify("Inline  code   and math") == "h-inline-code-and-math"


def test_rewrite_self_links_bare_fragment():
    md = "See the [Tables section](#tables) for details."
    out = rewrite_self_links(md, "https://outline.rvt/doc/gdc-abc123")
    assert (
        out == "See the [Tables section](https://outline.rvt/doc/gdc-abc123#h-tables) for details."
    )


def test_rewrite_self_links_leaves_external_links_alone():
    md = "A [plain hyperlink](https://www.getoutline.com) stays untouched."
    assert rewrite_self_links(md, "https://outline.rvt/doc/x") == md


def test_rewrite_self_links_multiple_fragments():
    md = "[a](#one) and [b](#two-words)"
    out = rewrite_self_links(md, "https://outline.rvt/doc/x")
    assert (
        out == "[a](https://outline.rvt/doc/x#h-one) and [b](https://outline.rvt/doc/x#h-two-words)"
    )
