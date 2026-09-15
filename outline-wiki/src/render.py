"""Render step: two independent outputs from the same `.qmd` source.

`extract_gfm` is a thin pass-through for the Outline/GFM path: no Quarto
invocation, so `` ```mermaid `` fences stay literal text for Outline's native
renderer instead of being executed/rasterized by Quarto.

`render_html` is the separate, Quarto-backed path for the standalone HTML
export (P1 requirement) and for the mermaid/LaTeX compile check used by
`validate.py`. It reuses the vendored `render_md.py`'s existing
mermaid-fence staging rather than reimplementing it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n\n?", re.DOTALL)
_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)

# render_md.py is vendored (copied from the render-md skill) so this repo has
# no cross-skill dependency. Override with RENDER_MD_SCRIPT to point at a
# different copy instead (e.g. to pick up render-md upstream changes).
RENDER_MD_SCRIPT = Path(os.environ.get("RENDER_MD_SCRIPT", Path(__file__).parent / "render_md.py"))


def read_front_matter(qmd_path: Path) -> dict:
    """Return the YAML front matter as a dict, or `{}` if there is none."""
    text = Path(qmd_path).read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def write_front_matter_field(qmd_path: Path, key: str, value: str) -> None:
    """Set a single front-matter field in place, touching nothing else in
    the file (title, body, other fields, formatting)."""
    path = Path(qmd_path)
    text = path.read_text(encoding="utf-8")
    line = yaml.safe_dump({key: value}, default_flow_style=False).strip()
    match = _FRONT_MATTER.match(text)

    if not match:
        path.write_text(f"---\n{line}\n---\n\n{text}", encoding="utf-8")
        return

    block = match.group(1)
    key_pattern = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    new_block = key_pattern.sub(line, block) if key_pattern.search(block) else f"{block}\n{line}"
    new_text = text[: match.start(1)] + new_block + text[match.end(1) :]
    path.write_text(new_text, encoding="utf-8")


def extract_gfm(qmd_path: Path) -> tuple[str, str]:
    """Strip front matter, return `(title, body)`. Everything else in the
    file (mermaid fences included) passes through unchanged."""
    path = Path(qmd_path)
    text = path.read_text(encoding="utf-8")
    match = _FRONT_MATTER.match(text)

    front_matter = yaml.safe_load(match.group(1)) or {} if match else {}
    body = text[match.end() :] if match else text

    title = front_matter.get("title")
    if not title:
        h1_match = _H1.search(body)
        title = h1_match.group(1).strip() if h1_match else path.stem

    return title, body


def render_html(qmd_path: Path, out_path: Path, theme: str | None = None) -> None:
    """Render `.qmd` -> self-contained HTML via the `render-md` skill."""
    cmd = [sys.executable, str(RENDER_MD_SCRIPT), str(qmd_path), "-o", str(out_path)]
    if theme:
        cmd += ["--theme", theme]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"error: render-md failed for {qmd_path}:\n{proc.stdout}\n{proc.stderr}")
