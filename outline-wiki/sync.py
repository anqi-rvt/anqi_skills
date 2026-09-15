"""Sync a `.qmd` source onto an Outline page. See design.md "Sync script".

    python sync.py INPUT.qmd [--manifest PATH] [--auto-commit] [--dry-run]

Front matter on `INPUT.qmd` carries the sync state:
- `outline_collection_id` (required on first sync)
- `outline_parent_id` (optional)
- `outline_id` (written back by this script after the first successful sync)
- `outline_last_synced_at` (written back after every push; used to detect
  manual edits made directly in Outline since the last sync)

Known v1 simplification: manual-edit reconciliation replaces the qmd's
entire body with the live Outline content rather than a fine-grained 3-way
merge. If you've also edited the qmd locally since the last sync, review the
diff carefully before trusting `--auto-commit`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

from anchors import rewrite_self_links
from manifest import Manifest
from outline_client import OutlineClient
from render import extract_gfm, read_front_matter, render_html, write_front_matter_field

_ASSET_REF = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")


def bot_reply_text(anchor_text: str) -> str:
    return (
        f"This thread was anchored to {anchor_text!r}. An automated sync of this "
        "page's content has reset that anchor — please re-check it still applies "
        "to the intended text."
    )


# -- pure logic (unit-tested) -----------------------------------------------


def normalize_table_whitespace(markdown: str) -> str:
    """Collapse GFM table padding differences (confirmed: Outline's markdown
    exporter re-pads `---` separators and cell content, even with no
    semantic change) so a parity check can compare content, not whitespace.
    """
    out_lines = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|") and _TABLE_ROW.match(line)):
            out_lines.append(line)
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and all(_SEPARATOR_CELL.match(c) for c in cells):
            normalized = [
                (":" if c.startswith(":") else "") + "---" + (":" if c.endswith(":") else "")
                for c in cells
            ]
        else:
            normalized = cells
        out_lines.append("|" + "|".join(f" {c} " for c in normalized) + "|" if normalized else line)
    return "\n".join(out_lines)


def texts_match(a: str, b: str) -> bool:
    """Round-trip parity check: equal once table padding is normalized."""
    return normalize_table_whitespace(a) == normalize_table_whitespace(b)


def rewrite_asset_links(markdown: str, url_map: dict[str, str]) -> str:
    for local_path, remote_url in url_map.items():
        markdown = markdown.replace(f"]({local_path})", f"]({remote_url})")
    return markdown


def find_local_asset_refs(markdown: str, base_dir: Path) -> list[Path]:
    """Distinct local files referenced via `![alt](path)` that exist on
    disk relative to `base_dir`. Already-resolved Outline attachment URLs
    and remote URLs are skipped."""
    base_dir = Path(base_dir)
    found: list[Path] = []
    for ref in _ASSET_REF.findall(markdown):
        if ref.startswith(("http://", "https://", "/api/")):
            continue
        candidate = base_dir / ref
        if candidate.exists() and candidate not in found:
            found.append(candidate)
    return found


# -- orchestration -----------------------------------------------------


def _git_commit(qmd_path: Path, message: str) -> None:
    subprocess.run(["git", "add", str(qmd_path)], check=True, cwd=qmd_path.parent)
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=qmd_path.parent)


def sync(
    qmd_path: Path, manifest_path: Path, auto_commit: bool = False, dry_run: bool = False
) -> int:
    qmd_path = Path(qmd_path)
    base_dir = qmd_path.parent
    cache_path = manifest_path.with_suffix(".last-synced.md")
    manifest = Manifest.load(manifest_path)

    front_matter = read_front_matter(qmd_path)
    document_id = front_matter.get("outline_id")
    collection_id = front_matter.get("outline_collection_id")
    parent_id = front_matter.get("outline_parent_id")
    last_synced_at = front_matter.get("outline_last_synced_at")

    if not document_id and not collection_id:
        raise SystemExit("error: qmd front matter needs outline_collection_id for a first sync")

    client = OutlineClient()

    # Step 5: reconcile manual edits (only possible once a document exists).
    if document_id and last_synced_at:
        live = client.get_document(document_id)
        if live["updatedAt"] != last_synced_at:
            cached = cache_path.read_text(encoding="utf-8") if cache_path.exists() else ""
            if not texts_match(cached, live["text"]):
                _, current_body = extract_gfm(qmd_path)
                if texts_match(current_body, live["text"]):
                    pass  # already matches (e.g. a prior run already reconciled this)
                else:
                    text = qmd_path.read_text(encoding="utf-8")
                    fm_match = re.match(r"^---\n.*?\n---\n\n?", text, re.DOTALL)
                    prefix = text[: fm_match.end()] if fm_match else ""
                    qmd_path.write_text(prefix + live["text"], encoding="utf-8")

                    _, patched_body = extract_gfm(qmd_path)
                    parity_ok = texts_match(patched_body, live["text"])

                    if parity_ok and auto_commit:
                        _git_commit(
                            qmd_path, f"outline-wiki: reconcile manual edit to {qmd_path.name}"
                        )
                    else:
                        reason = (
                            "parity check failed after patching"
                            if not parity_ok
                            else "review required"
                        )
                        raise SystemExit(
                            f"error: page was edited manually in Outline since the "
                            f"last sync ({reason}).\n"
                            f"  {qmd_path} has been updated with the live content and left dirty.\n"
                            "  Review the diff, commit it, and re-run the sync — "
                            "or pass --auto-commit to do this automatically next time."
                        )

    title, body = extract_gfm(qmd_path)

    if dry_run:
        cached = cache_path.read_text(encoding="utf-8") if cache_path.exists() else ""
        diff = "\n".join(difflib.unified_diff(cached.splitlines(), body.splitlines(), lineterm=""))
        print(f"[dry-run] title: {title}")
        print(f"[dry-run] local assets referenced: {len(find_local_asset_refs(body, base_dir))}")
        print("[dry-run] body diff vs. last sync:")
        print(diff or "(no change)")
        return 0

    # Step 4/5a: ensure a document id exists before uploading attachments.
    if not document_id:
        placeholder = client.create_document(title, "_Syncing…_", collection_id, parent_id)
        document_id = placeholder["id"]
        write_front_matter_field(qmd_path, "outline_id", document_id)

    # Steps 2-3: resolve + rewrite local asset references.
    url_map = {}
    for asset_path in find_local_asset_refs(body, base_dir):
        rel = str(asset_path.relative_to(base_dir)).replace("\\", "/")
        url_map[rel] = manifest.resolve(asset_path, client, document_id)
    body = rewrite_asset_links(body, url_map)

    # Self-referencing heading links: the document's URL is already known
    # from creation above (or from front matter on a prior sync), so this
    # is always a single pass — no need to push twice.
    page = client.get_document(document_id)
    body = rewrite_self_links(body, f"{client.base_url}{page['url']}")

    # Step 6: snapshot comments before overwriting.
    comments = client.list_comments(document_id, include_anchor_text=True)
    snapshot_path = manifest_path.with_suffix(".comments-snapshot.json")
    snapshot_path.write_text(json.dumps(comments, indent=2, default=str), encoding="utf-8")
    anchored_threads = [
        (c["id"], c["anchorText"])
        for c in comments
        if c.get("parentCommentId") is None and c.get("anchorText")
    ]

    # Step 7: snapshot revision (Outline versions on every update; this just
    # confirms one exists before we write).
    client.list_revisions(document_id)

    # Step 3 (HTML export / validation gate): render standalone HTML too.
    render_html(qmd_path, qmd_path.with_suffix(".html"))

    # Step 8: push.
    updated = client.update_document(document_id, text=body, title=title)

    # Step 9: mandatory bot reply on every previously-anchored thread —
    # anchor loss is unconditional on every resync, confirmed in design.md.
    # anchorText was captured above, before this push detaches it, so the
    # reply can still say what the comment used to point at.
    for thread_id, anchor_text in anchored_threads:
        client.create_comment(document_id, bot_reply_text(anchor_text), parent_comment_id=thread_id)

    # Step 10: record state for next sync's manual-edit check and manifest.
    write_front_matter_field(qmd_path, "outline_last_synced_at", updated["updatedAt"])
    cache_path.write_text(body, encoding="utf-8")
    manifest.save(manifest_path)

    print(f"synced: {client.base_url}{updated['url']}")
    if anchored_threads:
        print(f"posted anchor-reset replies on {len(anchored_threads)} thread(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sync.py", description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path, help="source .qmd file")
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="attachment manifest path (default: alongside input)",
    )
    p.add_argument(
        "--auto-commit", action="store_true", help="auto-commit manual-edit reconciliation patches"
    )
    p.add_argument("--dry-run", action="store_true", help="print what would change; no write calls")
    opts = p.parse_args(argv)

    if not opts.input.exists():
        p.error(f"input not found: {opts.input}")
    manifest_path = opts.manifest or opts.input.with_suffix(".manifest.json")

    return sync(opts.input, manifest_path, auto_commit=opts.auto_commit, dry_run=opts.dry_run)


if __name__ == "__main__":
    sys.exit(main())
