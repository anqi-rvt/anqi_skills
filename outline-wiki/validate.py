"""Local validation for a `.qmd` before it ever touches Outline.

    python validate.py INPUT.qmd

Checks, each reported independently rather than stopping at the first
failure: the mermaid/Quarto compile (via render.render_html — same error
output render-md itself produces), balanced math delimiters, and URL
syntax/reachability. Standalone for now; whether this becomes a pre-commit
hook or a pre-sync gate is a later decision (see design.md).
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

import requests

from render import extract_gfm, render_html

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)([^$\n]*)\$(?!\$)")
_BLOCK_MATH = re.compile(r"\$\$")


def check_math_delimiters(body: str) -> tuple[bool, str]:
    if _BLOCK_MATH.findall(body).__len__() % 2 != 0:
        return False, "unbalanced $$ block math delimiters"
    without_blocks = _BLOCK_MATH.sub("", body)
    if without_blocks.count("$") % 2 != 0:
        return False, "unbalanced $ inline math delimiters"
    return True, "balanced math delimiters"


def check_urls(body: str, timeout: float = 5.0) -> tuple[bool, str]:
    urls = [m for m in _LINK.findall(body) if m.startswith(("http://", "https://"))]
    if not urls:
        return True, "no external URLs to check"
    problems = []
    for url in urls:
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True)
            if r.status_code >= 400:
                problems.append(f"{url} -> HTTP {r.status_code}")
        except requests.RequestException as exc:
            problems.append(
                f"{url} -> unreachable ({exc.__class__.__name__}, may be internal-only)"
            )
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(urls)} URL(s) reachable"


def check_render(qmd_path: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.html"
        try:
            render_html(qmd_path, out)
        except SystemExit as exc:
            return False, str(exc)
    return True, "mermaid/Quarto compile succeeded"


def validate(qmd_path: Path) -> bool:
    _, body = extract_gfm(qmd_path)
    checks = [
        ("math delimiters", check_math_delimiters(body)),
        ("URLs", check_urls(body)),
        ("render", check_render(qmd_path)),
    ]
    all_ok = True
    for name, (ok, message) in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {message}")
        all_ok = all_ok and ok
    return all_ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="validate.py", description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path, help="source .qmd file")
    opts = p.parse_args(argv)

    if not opts.input.exists():
        p.error(f"input not found: {opts.input}")

    return 0 if validate(opts.input) else 1


if __name__ == "__main__":
    sys.exit(main())
