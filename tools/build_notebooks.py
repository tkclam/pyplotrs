#!/usr/bin/env python3
"""Execute the documentation notebooks under ``docs/notebooks/`` in place.

A dev tool, not part of the package. Run from the repo root::

    .venv/bin/python tools/build_notebooks.py            # execute and write
    .venv/bin/python tools/build_notebooks.py --check    # execute, write nothing

The notebooks are committed **with their outputs**, because that is what makes
them readable where people actually read them: rendered on GitHub, rendered into
the documentation site by ``mkdocs-jupyter`` (configured ``execute: false``, so
the docs build is deterministic and needs no kernel), and open-and-scroll in
nbviewer or Colab. The price is that the outputs are a build artifact living in
git, so they need a build tool that produces the *same* artifact twice - hence
this script rather than "whatever the last person's Run All left behind", which
is how the notebook this replaced grew to 4.5 MB of stale renders.

Three things here exist purely to keep the committed diff honest:

* **The font is pinned inside each notebook** (``set_font_family("Liberation
  Sans")``), not here, so a reader running the notebook gets the images that are
  committed next to it. Liberation Sans is compiled into the extension, so it
  resolves identically everywhere; left to itself pyplotrs would pick up the
  host's Arial or Helvetica and every glyph advance would move.
* **Timing metadata is off** (``record_timing=False``). nbclient otherwise
  stamps every cell with wall-clock start/end times, so a rebuild that changed
  nothing still rewrote every cell.
* **Kernel metadata is normalized** after the run: the interpreter's exact patch
  version is not a property of the notebook, and letting it through means the
  file diffs on any machine with a different Python.

``--check`` executes without writing, which is what CI runs: it proves every
cell still runs against the current API without asking a workflow to commit.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = ROOT / "docs" / "notebooks"

#: Cell metadata written by tooling rather than by the author. `execution`
#: holds nbclient's timing stamps; the rest are editor state (VS Code's
#: collapse flags, Colab's cell provenance) that no reader benefits from.
VOLATILE_CELL_METADATA = ("execution", "collapsed", "scrolled", "ExecuteTime",
                          "colab", "id", "outputId")

#: Fixed in place of whatever the executing kernel reports. `version` is the
#: only field that actually varies between machines, but pinning the whole
#: block keeps a future jupyter_client from introducing another one.
LANGUAGE_INFO = {
    "codemirror_mode": {"name": "ipython", "version": 3},
    "file_extension": ".py",
    "mimetype": "text/x-python",
    "name": "python",
    "nbconvert_exporter": "python",
    "pygments_lexer": "ipython3",
}

KERNELSPEC = {"display_name": "Python 3", "language": "python", "name": "python3"}


def normalize(nb) -> None:
    """Strip machine- and editor-specific metadata from an executed notebook.

    In place, on an ``nbformat`` NotebookNode. Everything removed here is either
    a timestamp, a path, or a version of something that is not the notebook.
    """
    nb.metadata["kernelspec"] = dict(KERNELSPEC)
    nb.metadata["language_info"] = copy.deepcopy(LANGUAGE_INFO)
    # `widgets` accumulates ipywidgets model state, which is large, opaque and
    # regenerated on every run; nothing here uses widgets.
    nb.metadata.pop("widgets", None)

    for cell in nb.cells:
        for key in VOLATILE_CELL_METADATA:
            cell.get("metadata", {}).pop(key, None)
        for output in cell.get("outputs", []):
            output.get("metadata", {}).pop("execution", None)
            # A traceback in a committed notebook is a build that should have
            # failed; `allow_errors=False` below means we never get here, but
            # an author's stray Run All could.
            if output.get("output_type") == "error":
                raise SystemExit(
                    f"error output left in {cell.get('id', '?')}: "
                    f"{output.get('ename')}: {output.get('evalue')}"
                )


def leaked_paths(nb, home: str) -> list[str]:
    """Output text that names the machine the notebook was built on.

    A committed notebook is published material; a printed ``/home/<someone>``
    or a temporary directory that only existed during the build is both a
    privacy leak and a line that will never be true for a reader.
    """
    hits = []
    for cell in nb.cells:
        for output in cell.get("outputs", []):
            for field in ("text", "evalue"):
                text = output.get(field)
                if isinstance(text, str) and home in text:
                    hits.append(text.strip()[:120])
            for mime, payload in (output.get("data") or {}).items():
                if mime.startswith("text/") and isinstance(payload, str) and home in payload:
                    hits.append(payload.strip()[:120])
    return hits


def execute(path: Path, write: bool) -> int:
    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.read(path, as_version=4)
    # 4.5 gave every cell a stable `id`. Without one, *anything* that reads the
    # notebook through nbformat rewrites the file to add them - including the
    # docs build, which would mean `mkdocs build` dirties the working tree.
    # `normalize` returns (number of changes, notebook), in that order.
    _, nb = nbformat.validator.normalize(nb)
    nb = nbformat.from_dict(nb)

    client = NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        record_timing=False,
        allow_errors=False,
        # Run with the notebook's own directory as the working directory, the
        # same as opening it in Jupyter, so a relative path in a cell means
        # what the reader will see it mean.
        resources={"metadata": {"path": str(path.parent)}},
    )
    # The `python3` kernelspec records argv[0] as a bare `python`, resolved
    # against PATH at launch. Running `.venv/bin/python tools/build_notebooks.py`
    # from a shell whose PATH points elsewhere would then execute the notebooks
    # against a different interpreter - one where `import pyplotrs` may well
    # succeed and be a different build. Pin it to the interpreter running this.
    client.kernel_manager_class = _pinned_kernel_manager()

    client.execute()
    normalize(nb)

    leaks = leaked_paths(nb, str(Path.home()))
    if leaks:
        print(f"  {path.name}: build-machine paths in output:", file=sys.stderr)
        for line in leaks:
            print(f"    {line}", file=sys.stderr)
        return 1

    executed = sum(1 for c in nb.cells if c.cell_type == "code")
    if write:
        # `json.dumps` rather than `nbformat.write`: identical content, but a
        # trailing newline and a fixed separator, so git sees a clean diff.
        text = json.dumps(nb, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        if path.read_text(encoding="utf-8") == text:
            print(f"  {path.name}: {executed} cells, unchanged")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"  {path.name}: {executed} cells, {len(text) / 1024:.0f} KB written")
    else:
        print(f"  {path.name}: {executed} cells ran")
    return 0


def _pinned_kernel_manager():
    from jupyter_client.manager import KernelManager

    class PinnedKernelManager(KernelManager):
        @property
        def kernel_spec(self):
            spec = super().kernel_spec
            if spec is not None and spec.argv and spec.argv[0] in ("python", "python3"):
                spec.argv = [sys.executable, *spec.argv[1:]]
            return spec

    return PinnedKernelManager


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="execute every notebook but write nothing (CI)")
    parser.add_argument("notebooks", nargs="*", type=Path,
                        help="notebooks to build (default: all of docs/notebooks)")
    args = parser.parse_args(argv)

    # The numbered prefix is the reading order, and it is also what marks a
    # notebook as part of the documentation set: a scratch notebook someone
    # leaves in the directory should not become a build step.
    paths = args.notebooks or sorted(NOTEBOOKS.glob("[0-9][0-9]_*.ipynb"))
    if not paths:
        print(f"error: no notebooks under {NOTEBOOKS.relative_to(ROOT)}", file=sys.stderr)
        return 1

    print(f"{'checking' if args.check else 'building'} {len(paths)} notebooks")
    failures = 0
    for path in paths:
        try:
            failures += execute(path, write=not args.check)
        except Exception as exc:  # noqa: BLE001 - the message is the product
            print(f"  {path.name}: FAILED - {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
