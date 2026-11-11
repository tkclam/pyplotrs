"""Render every example into docs/gallery/ for the documentation site.

uv run python tools/build_gallery.py
"""

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "gallery"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ["PYPLOTRS_EXAMPLES_OUT"] = str(OUT)
    for script in sorted((ROOT / "examples").glob("*.py")):
        print(f"running {script.name}")
        runpy.run_path(str(script), run_name="__main__")
    for f in OUT.iterdir():  # the site shows images; keep only those
        if f.suffix not in (".png", ".gif"):
            f.unlink()


if __name__ == "__main__":
    sys.exit(main())
