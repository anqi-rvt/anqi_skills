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

`example/test.qmd` is a working fixture exercising every requirement
(math, mermaid, images/GIF/SVG, video fallback, tables, self-referencing
anchors) — a good starting point to copy from, or to resync as a smoke test.

## Tests

```bash
pytest tests/
ruff check .
```

Unit tests cover the deterministic logic (attachment hashing/dedup, anchor
slugs, front-matter handling, table-parity normalization, asset-link
rewriting) with no network calls. `outline_client.py` and `sync.py`'s
orchestration are exercised live instead — via `--dry-run` and real runs —
the same way `render_md.py` (vendored here from the `render-md` skill) has
no test file and is validated by running it.
