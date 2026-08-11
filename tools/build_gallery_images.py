#!/usr/bin/env python3
"""Render every ``examples/*.py`` into ``docs/gallery/images/``.

A dev tool, not part of the package. Run from the repo root::

    .venv/bin/python tools/build_gallery_images.py

The gallery page includes each script verbatim through a ``--8<--`` snippet and
shows the image beside it, so the two have to agree;
``tests/test_examples.py`` compares them byte for byte.

**The body font is pinned to the bundled Liberation Sans**, which is the whole
reason this script exists rather than a shell loop. Left to itself, pyplotrs
resolves body text to the host's Arial or Helvetica if either is installed, so
the committed images could only be reproduced on a machine with the same fonts
- and CI, which has neither, would disagree with every one of them. Pinning
makes the gallery reproducible anywhere and shows what a reader who just ran
``pip install pyplotrs`` actually sees.
"""

from __future__ import annotations

import runpy
import shutil
import sys
import tempfile
from pathlib import Path

import pyplotrs as plt

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
IMAGES = ROOT / "docs" / "gallery" / "images"

#: What `tests/conftest.py` pins for the same reason. Both must agree, or the
#: suite compares images rendered with two different faces.
BUNDLED_FONT = "Liberation Sans"


def main() -> int:
    plt.set_font_family(BUNDLED_FONT)
    if plt.resolved_font_name() != BUNDLED_FONT:
        print(f"error: expected {BUNDLED_FONT!r}, resolved "
              f"{plt.resolved_font_name()!r}", file=sys.stderr)
        return 1

    IMAGES.mkdir(parents=True, exist_ok=True)
    scripts = sorted(EXAMPLES.glob("*.py"))
    if not scripts:
        print("error: no examples found", file=sys.stderr)
        return 1

    written, unchanged = 0, 0
    for script in scripts:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                # Each script saves to a bare relative filename, which is what
                # makes it copy-pasteable; run it somewhere disposable.
                import os
                os.chdir(tmp)
                runpy.run_path(str(script), run_name="__main__")
            finally:
                os.chdir(cwd)
            for produced in sorted(Path(tmp).iterdir()):
                if produced.suffix not in (".png", ".gif"):
                    continue
                target = IMAGES / produced.name
                if target.is_file() and target.read_bytes() == produced.read_bytes():
                    unchanged += 1
                    continue
                shutil.copy2(produced, target)
                written += 1
                print(f"  wrote {target.relative_to(ROOT)}")

    print(f"{written} written, {unchanged} unchanged, from {len(scripts)} scripts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
