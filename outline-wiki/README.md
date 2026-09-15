# outline-wiki

Sync a `.qmd` source onto an [Outline](https://www.getoutline.com) wiki page.
Git stays the source of truth, and team comments survive resyncs (with a
documented limitation; see `design.md`).

## Prerequisites

- Python 3.10+ (developed and tested on 3.12)
- [Quarto](https://quarto.org) on `PATH` (bundles its own Pandoc)
- `pip install -r requirements.txt`; add `-r requirements-dev.txt` too if
  you'll run the tests or linter

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OUTLINE_API_KEY` | yes | (none) | [Generate one](https://www.getoutline.com/developers#description/api-key) in Outline under Settings → API & Apps |
| `OUTLINE_URL` | no | `https://outline.rvt` | |
| `OUTLINE_INSECURE` | no | unset (verify on) | set `1` to skip TLS verification, internal CA only, never silent |

## Usage

```bash
# validate, then sync
python sync.py INPUT.qmd

# preview only, no writes
python sync.py INPUT.qmd --dry-run
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
front matter after the first successful sync; don't set them by hand.

| Flag | Effect |
|---|---|
| `--manifest PATH` | Attachment dedup manifest. Default: alongside input, `<name>.manifest.json`. |
| `--dry-run` | Print what would change; no write calls. |
| `--auto-commit` | Auto-commit a manual-edit reconciliation patch instead of leaving it dirty for review. |
| `--skip-validate` | Skip the pre-sync validation gate. |
| `--validate-only` | Run the validation gate only; don't sync. |

## Layout

```
outline-wiki/
├── sync.py       # entrypoint: validates, then syncs
├── src/          # outline_client, manifest, sync_metadata, anchors, render, validate, render_md
├── tests/        # pytest, no network calls
└── example/      # sample.qmd fixture, assets, generator script
```

### Example

`example/sample.qmd` exercises every requirement (math, mermaid, images/GIF/
SVG, video fallback, tables, self-referencing anchors) with no subject
matter of its own. Copy it as a starting point, or resync it as a smoke
test. `sample.html` is its checked-in standalone export.
`generate_sample_media.py` regenerates the placeholder assets (deps noted
at the top of that script, not in `requirements.txt` or
`requirements-dev.txt`, since nothing else needs them).

A sync writes one more file next to the `.qmd`:
`<name>.outline-wiki-metadata.json` (git-ignored). It holds the body as of
the last sync plus the comment/revision snapshots taken immediately before
the most recent push: bookkeeping the next sync reads back, not meant to
be durable history. The attachment manifest (`<name>.manifest.json`) is
separate and *is* tracked in git, since it can be shared across multiple
documents.

## Tests

```bash
pytest tests/
ruff check .
```

Unit tests cover the deterministic logic (hashing/dedup, anchor slugs,
front-matter handling, table-parity normalization, path-traversal
rejection). `sync.py`'s orchestration is exercised live instead, via
`--dry-run` and real runs.
