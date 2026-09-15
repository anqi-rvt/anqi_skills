---
name: outline-wiki
description: Sync a .qmd source onto an Outline wiki page (git stays the source of truth, team comments survive resyncs). Use when asked to publish/sync/update docs on Outline, or to validate a .qmd before syncing it.
---

# outline-wiki

See [README.md](README.md) for setup, usage, and CLI flags, and
[design.md](design.md) for the full design and empirical findings against
a real Outline workspace.

**Before onboarding real reviewers:** every `documents.update` call
unconditionally detaches the inline anchor of any human-created comment,
even a no-op resync. `sync.py` mitigates this with an automated reply on
each previously-anchored thread — see design.md's "Empirical tests"
section before relying on this with real feedback.

## Reporting back

After a sync, tell the user the resulting page URL, whether attachments
were newly uploaded vs. reused from the manifest, and whether any
anchor-reset replies were posted (and on how many threads).
