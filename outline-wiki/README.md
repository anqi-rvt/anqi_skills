# outline-wiki

Sync a `.qmd` source onto an [Outline](https://www.getoutline.com) wiki page —
git stays the source of truth, and team comments survive resyncs (with a
documented limitation; see `design.md`). Full design, requirements, and
empirical findings against a real Outline workspace live in `design.md`.

## Prerequisites

- Python 3.10+ (developed and tested on 3.12).
- [Quarto](https://quarto.org) on `PATH` — required for the standalone HTML
  export and for the mermaid/LaTeX compile check in `validate.py`. It bundles
  its own Pandoc; no Node or extra Python packages needed.
- An Outline API key in the `OUTLINE_API_KEY` environment variable, and
  optionally `OUTLINE_URL` (defaults to `https://outline.rvt`).
- TLS certificate verification is on by default. If your Outline instance
  sits behind an internal CA your machine doesn't trust, set
  `OUTLINE_INSECURE=1` explicitly — never silent, opt-in only.

Install the Python dependencies into whatever environment you use — a venv
isn't required, just recommended:

```bash
pip install -r requirements.txt
```

## Usage

```bash
# validate a .qmd compiles cleanly before touching Outline
python validate.py INPUT.qmd

# preview what a sync would change, no writes at all
python sync.py INPUT.qmd --dry-run

# sync for real
python sync.py INPUT.qmd
```

`INPUT.qmd` needs YAML front matter identifying where it goes:

```yaml
---
title: My Page
outline_collection_id: <collection-id>   # required on first sync
outline_parent_id: <parent-doc-id>       # optional
---
```

`sync.py` writes `outline_id` and `outline_last_synced_at` back into that
front matter after the first successful sync — don't set them by hand.

| Flag | Effect |
|---|---|
| `--manifest PATH` | Attachment dedup manifest. Default: alongside input, `<name>.manifest.json`. |
| `--dry-run` | Print what would change; no attachment upload, no document write, no comment post. |
| `--auto-commit` | If Outline was edited manually since the last sync, commit the reconciliation patch instead of leaving it dirty for review. |

`example/sample.qmd` is a working fixture exercising every requirement
(math, mermaid, images/GIF/SVG, video fallback, tables, self-referencing
anchors), with no subject matter of its own — a good starting point to copy
from, or to resync as a smoke test. `example/sample.html` is its checked-in
standalone HTML export. `example/generate_sample_media.py` regenerates the
placeholder image/GIF/MP4/SVG assets (needs `pillow`, `imageio`,
`imageio-ffmpeg` — not in `requirements.txt`, since nothing else in this
repo needs them).

## Tests

```bash
pytest tests/
ruff check .
```

Unit tests cover the deterministic logic (attachment hashing/dedup, anchor
slugs, front-matter handling, table-parity normalization, asset-link
rewriting, path-traversal rejection) with no network calls. `sync.py`'s
orchestration is exercised live instead — via `--dry-run` and real runs —
the same way `src/render_md.py` (vendored from a sibling project) has no
test file and is validated by running it.

## Layout

`sync.py` and `validate.py` are the only top-level scripts; everything they
import lives in `src/` (`outline_client.py`, `manifest.py`, `anchors.py`,
`render.py`, the vendored `render_md.py`). Tests stay in `tests/` and import
those modules directly (no package install needed — pytest's `pythonpath`
config in `pyproject.toml` handles it).
