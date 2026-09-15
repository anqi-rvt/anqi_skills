# outline-wiki

Sync a `.qmd` source onto an [Outline](https://www.getoutline.com) wiki page —
git stays the source of truth, and team comments survive resyncs (with a
documented limitation; see `design.md`).

## Prerequisites

- Python 3.10+ (developed and tested on 3.12)
- [Quarto](https://quarto.org) on `PATH` (bundles its own Pandoc)
- `pip install -r requirements.txt`

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OUTLINE_API_KEY` | yes | — | [Generate one](https://www.getoutline.com/developers#description/api-key) in Outline under Settings → API & Apps |
| `OUTLINE_URL` | no | `https://outline.rvt` | |
| `OUTLINE_INSECURE` | no | unset (verify on) | set `1` to skip TLS verification — internal CA only, never silent |

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
front matter after the first successful sync — don't set them by hand.

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
├── sync.py       # entrypoint — validates, then syncs
├── src/          # outline_client, manifest, anchors, render, validate, render_md
├── tests/        # pytest, no network calls
└── example/      # sample.qmd fixture, assets, generator script
```

### Example

`example/sample.qmd` exercises every requirement (math, mermaid, images/GIF/
SVG, video fallback, tables, self-referencing anchors) with no subject
matter of its own — copy it as a starting point, or resync it as a smoke
test. `sample.html` is its checked-in standalone export.
`generate_sample_media.py` regenerates the placeholder assets (deps noted
at the top of that script, not in `requirements.txt`).

## Tests

```bash
pytest tests/
ruff check .
```

Unit tests cover the deterministic logic (hashing/dedup, anchor slugs,
front-matter handling, table-parity normalization, path-traversal
rejection). `sync.py`'s orchestration is exercised live instead — via
`--dry-run` and real runs.
