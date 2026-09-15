---
name: outline-wiki
description: Sync a .qmd source onto an Outline wiki page (git stays the source of truth, team comments survive resyncs), plus a local validation script that checks mermaid/Quarto compile, math delimiters, and URLs before anything touches Outline. Use when asked to publish/sync/update docs on Outline, or to validate a .qmd before syncing it.
---

# outline-wiki

Publish a `.qmd` to Outline and keep it in sync — `sync.py` does the push;
`validate.py` checks the source compiles cleanly first. Full design,
requirements, and empirical findings live in `design.md`.

`example/test.qmd` exercises every P0/P1 requirement (math, mermaid,
images/GIF/SVG, video fallback, tables, self-referencing anchors) and is
kept synced to a real page (Core SW > Misc > "Outline Wiki Test Page") —
resync it after any change to `sync.py` as a smoke test.

## Run it

```bash
# validate first
~/venv/local/Scripts/python.exe ~/.claude/skills/outline-wiki/validate.py INPUT.qmd

# see what would change, no writes
~/venv/local/Scripts/python.exe ~/.claude/skills/outline-wiki/sync.py INPUT.qmd --dry-run

# sync for real
~/venv/local/Scripts/python.exe ~/.claude/skills/outline-wiki/sync.py INPUT.qmd
```

`OUTLINE_API_KEY` must be set (a permanent env var, not a temporary export —
see design.md's Sync script section). `INPUT.qmd` needs front matter:

```yaml
---
title: My Page
outline_collection_id: <collection-id>   # required on first sync
outline_parent_id: <parent-doc-id>       # optional
---
```

`outline_id` and `outline_last_synced_at` are written back into the front
matter automatically after the first successful sync — don't set them by
hand.

| Flag | Effect |
|---|---|
| `--manifest PATH` | Attachment dedup manifest. Default: alongside input, `<name>.manifest.json`. |
| `--dry-run` | Print what would change; no attachment upload, no document write, no comment post. |
| `--auto-commit` | If Outline was edited manually since the last sync, commit the reconciliation patch instead of leaving it dirty for review. |

## Why .qmd only, not .md

`.qmd` is a strict superset of GFM (YAML front matter, Quarto cross-refs,
callouts), and the standalone-HTML export already requires Quarto — so
there's no format-detection branch to maintain. Mermaid fences stay literal
text either way: the Outline/GFM path never invokes Quarto (avoids Quarto
rasterizing what should stay a live-rendered `` ```mermaid `` block), while
the HTML path reuses `render_md.py`'s Quarto staging (vendored here from the
`render-md` skill, so this repo has no cross-skill dependency).

## What's confirmed vs. what's a v1 simplification

Every mechanism `sync.py` relies on (attachment upload flow, comment
schema, anchor slug format, table re-padding on export) was empirically
validated against the real Rivet Outline workspace — see design.md's
"Empirical tests" section for the specifics and how each was tested.

One deliberate simplification: manual-edit reconciliation replaces the
`.qmd`'s entire body with Outline's live content rather than attempting a
fine-grained three-way merge. If the source was also edited locally since
the last sync, review the diff before trusting `--auto-commit` — it's safe
(never loses the Outline side), just not surgical.

## Comment anchoring: the one thing to know before onboarding reviewers

Confirmed, not hypothetical: every `documents.update` call — even pushing
back byte-identical content — unconditionally detaches the inline anchor of
any comment a human added by selecting text in the UI. The comment itself
never gets lost, only where it's pinned in the page. `sync.py` handles this
by posting an automatic reply on every previously-anchored thread after each
push, asking the reviewer to re-check it still applies — this happens on
every sync with pre-existing anchored comments, not just when content
actually changed.

## Setup

Requires the shared venv (`~/venv/local/`) with `requirements.txt` installed
(`requests`, `pyyaml`, `pytest`, `ruff`) and Quarto on `PATH`. See `README.md`
for the portable (non-venv-specific) version of this.

```bash
~/venv/local/Scripts/python.exe -m pytest ~/.claude/skills/outline-wiki/tests/
```

## Reporting back

After a sync, tell the user the resulting page URL, whether any attachments
were newly uploaded vs. reused from the manifest, and whether any bot replies
were posted (and on how many threads) — that's the signal reviewers need to
know a comment's anchor may have moved.
