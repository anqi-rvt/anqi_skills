---
name: outline-wiki
description: Sync a .qmd source onto an Outline wiki page (git stays the source of truth, team comments survive resyncs). Use when asked to publish/sync/update docs on Outline, or to validate a .qmd before syncing it.
---

# outline-wiki

See [README.md](README.md) for setup, usage, and CLI flags, and
[design.md](design.md) for the full design and empirical findings against
a real Outline workspace.

> **WARNING — comment anchors reset on every sync.** Outline's
> `documents.update` unconditionally detaches the inline anchor of any
> human-created comment, even on a no-op resync. `sync.py` mitigates this
> with an automated reply on each previously-anchored thread, quoting the
> original anchor text — see design.md's "Comment anchoring" section for
> the full mechanism.

## Reporting back

After a sync, report:

- **Page**: the resulting Outline URL.
- **Local files**: absolute paths to the synced `.qmd`, its `.html`
  export, and the manifest — never relative paths.
- **Attachments**: count newly uploaded vs. reused from the manifest.
- **Comments**: count of anchor-reset replies posted, and on how many
  threads.

After a validation-only or dry run, report each check's pass/fail (or the
diff) instead — see README.md's flag table.
