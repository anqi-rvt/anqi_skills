#!/usr/bin/env python3
"""
render_md.py - compile a Markdown file (with mermaid diagrams) to deterministic,
self-contained HTML via Quarto.

Why this wrapper exists
-----------------------
Quarto renders plain `.md` fine, but its mermaid support is tied to the
*executable cell* dialect:

  * `.md`  + ```mermaid    -> renders, but mermaid.js is NOT bundled.
                              Diagrams appear as preformatted text. Silent failure.
  * `.md`  + ```{mermaid}  -> hard error:
                              "You must use the .qmd extension for documents with
                               executable code."
  * `.qmd` + ```{mermaid}  -> works; mermaid.js is bundled.

So the only working path from a portable, GitHub-flavoured `.md` is to stage a
temporary `.qmd` with the fences rewritten. That is what this script does, then
cleans up after itself so the source tree keeps exactly one `.md`.

Determinism
-----------
For a fixed (Quarto version, input bytes, options) triple the output is
byte-identical - verified by repeat renders. Two caveats worth knowing:

  * The HTML carries `<meta name="generator" content="quarto-X.Y.Z">` and inlines
    Quarto's bundled JS/CSS, so upgrading Quarto changes the bytes.
  * Diagrams render client-side from the *embedded* mermaid.js. The visual is
    therefore pinned to the file and works offline, but it is produced by the
    reader's browser, not baked into the HTML as SVG.

Usage
-----
    python render_md.py INPUT.md [-o OUTPUT.html] [options]
    python render_md.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Quarto locations to probe on Windows when it is not on PATH. A fresh install
# updates the machine PATH, but already-running shells keep the stale copy, so
# probing avoids a confusing "not found" right after installing.
#
# .exe first, deliberately: the sibling quarto.cmd is a batch shim, and routing a
# space-containing path through `cmd /c` hits cmd.exe's quote-stripping rule and
# fails with "'C:\Program' is not recognized". The .exe has no such problem.
WINDOWS_ROOTS = [
    r"C:\Program Files\Quarto\bin",
    r"C:\Program Files (x86)\Quarto\bin",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Quarto\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Quarto\bin"),
]
WINDOWS_CANDIDATES = [
    str(Path(root) / name) for root in WINDOWS_ROOTS for name in ("quarto.exe", "quarto.cmd")
]

FENCE_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
MERMAID_INFO_RE = re.compile(r"^\{?mermaid\}?\s*$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Quarto discovery
# --------------------------------------------------------------------------- #


def find_quarto(explicit: str | None = None) -> str:
    """Return a runnable path to quarto, or raise with an actionable message."""
    if explicit:
        if Path(explicit).exists():
            return explicit
        raise SystemExit(f"error: --quarto path does not exist: {explicit}")

    found = shutil.which("quarto")
    if found:
        # If PATH resolved to the batch shim, prefer the sibling .exe.
        if os.name == "nt" and found.lower().endswith(".cmd"):
            exe = Path(found).with_name("quarto.exe")
            if exe.exists():
                return str(exe)
        return found

    if os.name == "nt":
        for cand in WINDOWS_CANDIDATES:
            if cand and Path(cand).exists():
                return cand

    raise SystemExit(
        "error: quarto not found.\n"
        "  Install:  winget install --id Posit.Quarto\n"
        "            (macOS)  brew install --cask quarto\n"
        "            (Linux)  https://quarto.org/docs/get-started/\n"
        "  If you just installed it, open a NEW shell so PATH refreshes,\n"
        "  or pass --quarto <path-to-quarto>."
    )


def quarto_argv(quarto: str, args: list[str]) -> list[str]:
    """
    Invoke the executable directly.

    Note the absence of a `cmd /c` wrapper: it is what a naive port would reach
    for on Windows, but cmd.exe strips the outer quotes of a quoted program path,
    so "C:\\Program Files\\..." breaks at the space. Python launches both .exe and
    .cmd targets fine on its own, and find_quarto() prefers the .exe anyway.
    """
    return [quarto, *args]


def quarto_version(quarto: str) -> str:
    out = subprocess.run(
        quarto_argv(quarto, ["--version"]),
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        (out.stdout or out.stderr).strip().splitlines()[0]
        if out.stdout or out.stderr
        else "unknown"
    )


# --------------------------------------------------------------------------- #
# Markdown transforms
# --------------------------------------------------------------------------- #


def rewrite_mermaid_fences(text: str) -> tuple[str, int]:
    """
    Rewrite top-level ```mermaid fences to ```{mermaid}.

    Uses a fence state machine rather than a blind regex so that a mermaid fence
    *nested inside* another fenced block - e.g. a ```markdown example that shows
    mermaid source - is left alone. Blind substitution would corrupt those.
    """
    lines = text.split("\n")
    out: list[str] = []
    open_marker: str | None = None  # the exact fence that opened the current block
    count = 0

    for line in lines:
        m = FENCE_RE.match(line)

        if open_marker is None:
            if m:
                marker, info = m.group("marker"), m.group("info").strip()
                if MERMAID_INFO_RE.match(info):
                    out.append(f"{m.group('indent')}{marker}{{mermaid}}")
                    open_marker = marker
                    count += 1
                    continue
                open_marker = marker
            out.append(line)
            continue

        # Inside a fenced block: only a closing fence of the same char and at
        # least the same length ends it.
        if m and not m.group("info").strip():
            marker = m.group("marker")
            if marker[0] == open_marker[0] and len(marker) >= len(open_marker):
                open_marker = None
        out.append(line)

    return "\n".join(out), count


def split_front_matter(text: str) -> tuple[str | None, str]:
    """Return (yaml_without_delimiters, body). yaml is None when absent."""
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, flags=re.DOTALL)
    if not m:
        return None, text
    return m.group(1), text[m.end() :]


def build_front_matter(existing: str | None, opts: argparse.Namespace, title: str) -> str:
    """
    Compose YAML front matter.

    If the source already declares `format:`, it is trusted verbatim and only a
    title is added when missing - the author's intent wins over our defaults.
    """
    if existing and re.search(r"^format\s*:", existing, flags=re.M):
        block = existing
        if not re.search(r"^title\s*:", block, flags=re.M):
            block = f'title: "{title}"\n' + block
        return f"---\n{block}\n---\n\n"

    lines: list[str] = []
    if existing:
        lines.append(existing.rstrip("\n"))
    if not (existing and re.search(r"^title\s*:", existing, flags=re.M)):
        lines.append(f'title: "{title}"')

    fmt = [
        "format:",
        "  html:",
        f"    embed-resources: {'true' if opts.self_contained else 'false'}",
        f"    toc: {'true' if opts.toc else 'false'}",
        f"    toc-depth: {opts.toc_depth}",
        "    toc-location: left",
        f"    theme: {opts.theme}",
        "    code-copy: true",
        "    df-print: default",
        "    link-external-newwindow: true",
    ]
    if opts.max_width:
        fmt.append(f"    max-width: {opts.max_width}")
    lines.extend(fmt)
    return "---\n" + "\n".join(lines) + "\n---\n\n"


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #


def render(opts: argparse.Namespace) -> int:
    src = Path(opts.input).resolve()
    if not src.is_file():
        raise SystemExit(f"error: input not found: {src}")

    quarto = find_quarto(opts.quarto)
    out_path = Path(opts.output).resolve() if opts.output else src.with_suffix(".html")

    text = src.read_text(encoding="utf-8")
    existing_yaml, body = split_front_matter(text)
    body, n_diagrams = rewrite_mermaid_fences(body)

    title = opts.title
    if not title:
        m = re.search(r"^#\s+(.+?)\s*$", body, flags=re.M)
        title = m.group(1) if m else src.stem
        title = re.sub(r"[`*_]", "", title)

    staged = build_front_matter(existing_yaml, opts, title) + body

    # The temp .qmd must live beside the source: Quarto resolves relative links,
    # images and includes relative to the input file, not the CWD.
    tmp_qmd = src.with_name(f".{src.stem}.render-md-{os.getpid()}.qmd")
    produced = tmp_qmd.with_suffix(".html")
    tmp_files_dir = tmp_qmd.with_name(tmp_qmd.stem + "_files")

    try:
        tmp_qmd.write_text(staged, encoding="utf-8", newline="\n")

        cmd = quarto_argv(quarto, ["render", str(tmp_qmd), "--to", "html"])
        if opts.verbose:
            print(f"$ {' '.join(cmd)}", file=sys.stderr)

        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(src.parent))
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout or "")
            sys.stderr.write(proc.stderr or "")
            raise SystemExit(f"error: quarto render failed (exit {proc.returncode})")

        if not produced.exists():
            raise SystemExit(f"error: quarto reported success but {produced.name} is missing")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(out_path))

        if tmp_files_dir.is_dir():
            if opts.self_contained:
                shutil.rmtree(tmp_files_dir, ignore_errors=True)
            else:
                final_files = out_path.with_name(out_path.stem + "_files")
                shutil.rmtree(final_files, ignore_errors=True)
                shutil.move(str(tmp_files_dir), str(final_files))
    finally:
        if not opts.keep_qmd:
            tmp_qmd.unlink(missing_ok=True)
        elif tmp_qmd.exists():
            kept = src.with_suffix(".qmd")
            shutil.move(str(tmp_qmd), str(kept))
            print(f"kept staged source: {kept}")

    size = out_path.stat().st_size
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()

    print(f"rendered   {src.name} -> {out_path}")
    print(f"  diagrams {n_diagrams} mermaid block(s) rewritten to executable cells")
    print(
        f"  size     {size / 1_000_000:.2f} MB"
        + ("  (self-contained, offline)" if opts.self_contained else "  (+ _files/ sidecar)")
    )
    print(f"  quarto   {quarto_version(quarto)}")
    print(f"  sha256   {digest}")
    return 0


def check() -> int:
    print("render-md environment check")
    try:
        quarto = find_quarto(None)
    except SystemExit as e:
        print(f"  quarto   MISSING\n{e}")
        return 1
    print(f"  quarto   {quarto_version(quarto)}")
    print(f"  path     {quarto}")
    print(f"  python   {sys.version.split()[0]}")
    print("  ready.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="render-md",
        description="Compile Markdown (with mermaid) to deterministic self-contained HTML "
        "via Quarto.",
    )
    p.add_argument("input", nargs="?", help="input .md file")
    p.add_argument("-o", "--output", help="output .html path (default: alongside input)")
    p.add_argument("--title", help="document title (default: first H1, else filename)")
    p.add_argument(
        "--theme",
        default="cosmo",
        help="Quarto/Bootswatch theme, e.g. cosmo, flatly, darkly, litera (default: cosmo)",
    )
    p.add_argument("--toc-depth", type=int, default=4, help="TOC depth (default: 4)")
    p.add_argument(
        "--no-toc", dest="toc", action="store_false", help="disable the table of contents"
    )
    p.add_argument("--max-width", help="content max width, e.g. 1200px")
    p.add_argument(
        "--no-self-contained",
        dest="self_contained",
        action="store_false",
        help="emit a _files/ sidecar instead of one embedded file",
    )
    p.add_argument(
        "--keep-qmd", action="store_true", help="keep the staged .qmd next to the source"
    )
    p.add_argument("--quarto", help="explicit path to the quarto executable")
    p.add_argument("--check", action="store_true", help="verify the toolchain and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(toc=True, self_contained=True)

    opts = p.parse_args()
    if opts.check:
        return check()
    if not opts.input:
        p.error("input is required (or pass --check)")
    return render(opts)


if __name__ == "__main__":
    sys.exit(main())
