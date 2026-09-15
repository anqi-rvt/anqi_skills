"""Heading-anchor slugs for Outline links.

Confirmed empirically (see design.md): a heading-section link needs
`page-url#h-<slug>`, where `<slug>` is the heading text lowercased with
spaces turned into hyphens. Punctuation-stripping rules beyond spaces are
unverified, so this normalizes conservatively (drop anything that isn't
alphanumeric or a hyphen) rather than assuming Outline's exact behavior.
"""

from __future__ import annotations

import re

_FRAGMENT_LINK = re.compile(r"\]\(#([^)]+)\)")


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9-]", "", text)
    text = re.sub(r"-{2,}", "-", text)  # stripped punctuation can leave doubled hyphens
    return text.strip("-")


def slugify(heading_text: str) -> str:
    """Turn heading text into Outline's confirmed `h-<slug>` anchor id."""
    return f"h-{_normalize(heading_text)}"


def rewrite_self_links(markdown: str, page_url: str) -> str:
    """Rewrite bare `[text](#fragment)` links into `page_url#h-<slug>`.

    Leaves any link whose target isn't a bare `#fragment` (external URLs,
    already-resolved page links) untouched.
    """

    def replace(match: re.Match[str]) -> str:
        fragment = _normalize(match.group(1))
        return f"]({page_url}#h-{fragment})"

    return _FRAGMENT_LINK.sub(replace, markdown)
