"""The documentation notebooks have to run, and to stay wired into the docs.

`docs/notebooks/*.ipynb` is the tutorial material: eight documents committed
*with their output*, rendered into the site by mkdocs-jupyter with `execute:
false` and read on GitHub the same way. That combination is exactly the one that
rots
quietly — the site and the repository both show images that were true once, and
nothing re-runs the code that made them.

So this module asserts three things:

* **Every code cell still runs** against the library as it is now. The cells are
  executed in-process rather than through a kernel: it needs no Jupyter in the
  test environment, it is fast enough to run on every `pytest`, and a rename in
  `Axes` fails here rather than in a screenshot. (CI additionally runs
  `tools/build_notebooks.py --check`, which drives a real kernel.)
* **The committed output is actually there**, because a notebook whose outputs
  were stripped renders as a blank page on the site and on GitHub.
* **Every notebook is reachable** — listed on the overview page and in the
  MkDocs nav — since a notebook nobody links to is a file that only the tests
  ever open.

Notebooks that need an optional dependency (matplotlib, NumPy, IPython) are
skipped rather than failed when it is missing: the test environment is
deliberately close to stdlib-only, and the two notebooks that reach for one are
*about* comparing against matplotlib.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = ROOT / "docs" / "notebooks"
#: The numbered prefix is both the reading order and the marker of a notebook
#: that belongs to the documentation set; see `tools/build_notebooks.py`.
NOTEBOOKS = sorted(NOTEBOOK_DIR.glob("[0-9][0-9]_*.ipynb"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def code_cells(notebook: dict) -> list[str]:
    """The code cells, with IPython line magics stripped.

    `%matplotlib inline` is a magic, not Python; it is meaningful in a kernel
    and a syntax error under `exec`. Dropping the line is right rather than
    lossy - it selects a display backend and computes nothing.
    """
    sources = []
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        lines = [line for line in "".join(cell["source"]).splitlines()
                 if not line.lstrip().startswith(("%", "!"))]
        sources.append("\n".join(lines))
    return sources


def imported_modules(source: str) -> set[str]:
    """Top-level module names imported anywhere in `source`."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_notebook_set_is_present():
    """Guard the guard: an empty glob would make every check below vacuous."""
    assert len(NOTEBOOKS) == 8, (
        f"expected the eight documentation notebooks, found "
        f"{[p.name for p in NOTEBOOKS]}"
    )


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_notebook_is_wellformed(path):
    notebook = load(path)

    assert notebook["nbformat"] == 4
    # 4.5 gave every cell a stable `id`. Without one, anything that reads the
    # file through nbformat rewrites it to add them - including `mkdocs build`,
    # which would then dirty the working tree on a docs build.
    assert notebook["nbformat_minor"] >= 5, "notebook predates stable cell ids"
    for cell in notebook["cells"]:
        assert cell.get("id"), "a cell has no id; run tools/build_notebooks.py"

    first = notebook["cells"][0]
    assert first["cell_type"] == "markdown", "a notebook should open with prose"
    assert "".join(first["source"]).lstrip().startswith("# "), (
        "the first cell must carry the page's H1 - it becomes the site's title"
    )


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_notebook_carries_its_output(path):
    """A stripped notebook renders as a blank page on the site and on GitHub."""
    cells = [c for c in load(path)["cells"] if c["cell_type"] == "code"]
    with_output = [c for c in cells if c.get("outputs")]

    assert len(with_output) >= len(cells) // 2, (
        f"{path.name}: only {len(with_output)} of {len(cells)} code cells have "
        f"committed output; re-run tools/build_notebooks.py"
    )
    images = sum(1 for c in cells for o in c.get("outputs", [])
                 for mime in (o.get("data") or {}) if mime.startswith("image/"))
    assert images, f"{path.name} committed no figures"


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_notebook_output_names_no_machine(path):
    """Committed output is published material, so it must not name a host.

    A printed home directory is both a privacy leak and a line that will never
    be true for a reader. `tools/build_notebooks.py` refuses to write one; this
    catches a notebook saved from an editor instead.
    """
    for cell in load(path)["cells"]:
        for output in cell.get("outputs", []):
            payloads = [output.get("text", "")]
            payloads += [v for k, v in (output.get("data") or {}).items()
                         if k.startswith("text/")]
            for payload in payloads:
                joined = "".join(payload)
                assert not re.search(r"/(?:home|Users)/[A-Za-z0-9._-]+", joined), (
                    f"{path.name}: output names a home directory"
                )


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_notebook_still_runs(path, tmp_path, monkeypatch):
    """Execute every code cell in one namespace, as a kernel would.

    In-process rather than through Jupyter so that this runs in the ordinary
    test environment. The cells write into `tmp_path` because several of them
    save files, and a notebook that littered the repository would be a bug in
    the notebook.
    """
    source = "\n".join(code_cells(load(path)))

    for module in sorted(imported_modules(source)):
        if module in ("math", "random", "re", "io", "os", "sys", "time", "json",
                      "tempfile", "pathlib", "datetime", "subprocess",
                      "concurrent", "itertools", "textwrap"):
            continue
        if importlib.util.find_spec(module) is None:
            pytest.skip(f"{path.name} needs {module}, which is not installed")

    monkeypatch.chdir(tmp_path)
    namespace = {"__name__": "__main__", "__file__": str(path)}
    for number, cell in enumerate(code_cells(load(path)), start=1):
        try:
            exec(compile(cell, f"{path.name}:cell{number}", "exec"), namespace)
        except Exception as exc:  # noqa: BLE001 - the message is the product
            pytest.fail(f"{path.name} cell {number} raised "
                        f"{type(exc).__name__}: {exc}\n\n{cell}")


def test_every_notebook_is_listed_on_the_overview_page():
    """A notebook nobody links to is a file only the tests ever open."""
    index = (NOTEBOOK_DIR / "index.md").read_text(encoding="utf-8")
    for path in NOTEBOOKS:
        assert f"({path.name})" in index, (
            f"{path.name} is not linked from docs/notebooks/index.md"
        )


def test_every_notebook_is_in_the_mkdocs_nav():
    """…and one that is not in the nav is not on the site at all."""
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    for path in NOTEBOOKS:
        assert f"notebooks/{path.name}" in config, (
            f"{path.name} is missing from the nav in mkdocs.yml"
        )
    assert "mkdocs-jupyter" in config, (
        "the notebooks are in the nav but the plugin that renders them is not "
        "configured, so `mkdocs build --strict` will fail"
    )


@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.stem for p in NOTEBOOKS])
def test_cross_links_between_notebooks_resolve(path):
    """`[text](04_….ipynb)` links are hand-written, so they can be wrong."""
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\(([0-9]{2}_[a-z_]+\.ipynb)\)", text):
        assert (NOTEBOOK_DIR / target).is_file(), (
            f"{path.name} links to {target}, which does not exist"
        )
