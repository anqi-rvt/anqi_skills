"""Sync a `.qmd` source onto an Outline page. See design.md "Sync script".

    python sync.py INPUT.qmd [--manifest PATH] [--auto-commit] [--dry-run]
                              [--skip-validate | --validate-only]

Runs validate.py's checks (mermaid/Quarto compile, math delimiters, URLs)
as a gate before every sync, unless --skip-validate is passed. Pass
--validate-only to run just that gate and exit, without syncing.

Front matter on `INPUT.qmd` carries the sync state:
- `outline_collection_id` (required on first sync)
- `outline_parent_id` (optional)
- `outline_id` (written back by this script after the first successful sync)
- `outline_last_synced_at` (written back after every push; used to detect
  manual edits made directly in Outline since the last sync)

Manual-edit reconciliation replaces the qmd's entire body with the live
Outline content — a whole-file replace, not a merge. If the qmd was also
edited locally since the last sync, review the diff before trusting
`--auto-commit`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from anchors import rewrite_self_links  # noqa: E402
from manifest import Manifest  # noqa: E402
from outline_client import OutlineClient  # noqa: E402
from render import (  # noqa: E402
    extract_gfm,
    read_front_matter,
    render_html,
    write_front_matter_field,
)
from validate import validate  # noqa: E402

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
    disk within `base_dir`. Already-resolved Outline attachment URLs and
    remote URLs are skipped; a reference that escapes `base_dir` (`../`
    traversal, or an absolute path) is rejected rather than uploaded —
    a malformed/malicious `.qmd` must not be able to exfiltrate an
    arbitrary local file as an Outline attachment."""
    base_dir = Path(base_dir).resolve()
    found: list[Path] = []
    for ref in _ASSET_REF.findall(markdown):
        if ref.startswith(("http://", "https://", "/api/")):
            continue
        candidate = (base_dir / ref).resolve()
        if not candidate.is_relative_to(base_dir):
            continue
        if candidate.exists() and candidate not in found:
            found.append(candidate)
    return found


# -- orchestration -----------------------------------------------------


def _git_commit(qmd_path: Path, message: str) -> None:
    try:
        subprocess.run(["git", "add", str(qmd_path)], check=True, cwd=qmd_path.parent)
        subprocess.run(["git", "commit", "-m", message], check=True, cwd=qmd_path.parent)
    except FileNotFoundError as exc:
        raise SystemExit(
            "error: --auto-commit needs git on PATH, but it wasn't found. "
            f"{qmd_path} has already been patched with the reconciled content — "
            "commit it yourself."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"error: --auto-commit's `git {exc.cmd[1]}` failed (is {qmd_path.parent} "
            f"a git repository?). {qmd_path} has already been patched with the "
            "reconciled content — commit it yourself."
        ) from exc


def sync(
    qmd_path: Path, manifest_path: Path, auto_commit: bool = False, dry_run: bool = False
) -> int:
    qmd_path = Path(qmd_path)
    # Resolved: find_local_asset_refs returns resolved paths (for the
    # traversal check), and relative_to() below needs both sides resolved
    # consistently.
    base_dir = qmd_path.parent.resolve()
    # Derived from qmd_path, not manifest_path: the manifest may be shared
    # across multiple documents (hash-keyed dedup across renamed/moved
    # files), but the sync cache/snapshots below are specific to this one.
    cache_path = qmd_path.with_suffix(".last-synced.md")
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
                elif dry_run:
                    print(
                        f"[dry-run] {qmd_path} was edited manually in Outline since the "
                        "last sync — a real run would patch it with the live content and "
                        "stop for review (or auto-commit with --auto-commit). No files "
                        "touched."
                    )
                    return 0
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
    asset_paths = find_local_asset_refs(body, base_dir)
    for asset_path in asset_paths:
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
    comments_snapshot_path = qmd_path.with_suffix(".comments-snapshot.json")
    comments_snapshot_path.write_text(json.dumps(comments, indent=2, default=str), encoding="utf-8")
    anchored_threads = [
        (c["id"], c["anchorText"])
        for c in comments
        if c.get("parentCommentId") is None and c.get("anchorText")
    ]

    # Step 7: snapshot the page's revision history before writing, so this
    # sync is rollback-able independent of git history.
    revisions = client.list_revisions(document_id)
    revisions_snapshot_path = qmd_path.with_suffix(".revisions-snapshot.json")
    revisions_snapshot_path.write_text(
        json.dumps(revisions, indent=2, default=str), encoding="utf-8"
    )

    # Step 3 (standalone HTML export, P1 requirement): the validation gate
    # in main() already confirmed this compiles — this call writes the
    # persistent output file, not a throwaway check.
    html_path = qmd_path.with_suffix(".html")
    render_html(qmd_path, html_path)

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

    new_uploads = len(manifest.newly_uploaded)
    reused_uploads = len(asset_paths) - new_uploads

    print(f"Page: {client.base_url}{updated['url']}")
    print(
        "Local files: "
        f"qmd={qmd_path.resolve()} "
        f"html={html_path.resolve()} "
        f"manifest={manifest_path.resolve()}"
    )
    print(f"Attachments: {new_uploads} uploaded, {reused_uploads} reused")
    reply_word = "reply" if len(anchored_threads) == 1 else "replies"
    print(f"Comments: {len(anchored_threads)} anchor-reset {reply_word} posted")
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
    validate_group = p.add_mutually_exclusive_group()
    validate_group.add_argument(
        "--skip-validate", action="store_true", help="skip the pre-sync validation gate"
    )
    validate_group.add_argument(
        "--validate-only", action="store_true", help="run the validation gate only; do not sync"
    )
    opts = p.parse_args(argv)

    if not opts.input.exists():
        p.error(f"input not found: {opts.input}")

    if opts.validate_only:
        return 0 if validate(opts.input) else 1

    if not opts.skip_validate and not validate(opts.input):
        print(
            "error: validation failed — fix the issues above, or pass --skip-validate to "
            "sync anyway",
            file=sys.stderr,
        )
        return 1

    manifest_path = opts.manifest or opts.input.with_suffix(".manifest.json")
    return sync(opts.input, manifest_path, auto_commit=opts.auto_commit, dry_run=opts.dry_run)


if __name__ == "__main__":
    sys.exit(main())
