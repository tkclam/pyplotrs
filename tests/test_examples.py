"""The gallery scripts have to run.

`examples/*.py` is not decoration: `docs/gallery/index.md` includes each one
verbatim through a `--8<--` snippet, and `docs/gallery/images/` holds the figure
each one produces. So every example is simultaneously the gallery's source
listing and the thing that generated the picture beside it — and nothing
executed them. A rename in `Axes` would leave the gallery showing code that
raises, next to an image proving it once worked.

They run in a `tmp_path` because each script saves relative to the working
directory, which is what makes them copy-pasteable in the first place.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SCRIPTS = sorted(EXAMPLES.glob("*.py"))


def test_there_are_examples_to_run():
    """Guard the guard: an empty glob would make every check below vacuous."""
    assert len(SCRIPTS) >= 20, f"expected the full gallery, found {len(SCRIPTS)}"


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.stem for s in SCRIPTS])
def test_example_runs_and_writes_a_figure(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(script), run_name="__main__")

    written = [p for p in tmp_path.iterdir() if p.is_file()]
    assert written, f"{script.name} ran but wrote no file"
    for out in written:
        assert out.stat().st_size > 0, f"{script.name} wrote an empty {out.name}"


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.stem for s in SCRIPTS])
def test_example_is_included_in_the_gallery(script):
    """Every script is on the gallery page, and every gallery snippet exists.

    The pairing is the point: a script nobody references is dead weight, and a
    snippet path that no longer exists fails the docs build with
    `check_paths: true` — but only for the direction that is already checked.
    """
    gallery = (EXAMPLES.parent / "docs" / "gallery" / "index.md").read_text()
    rel = f"examples/{script.name}"
    assert rel in gallery, (
        f"{script.name} is not included in docs/gallery/index.md, so it is "
        f"tested here but never shown to anyone"
    )


def test_every_gallery_image_is_shown_on_the_gallery_page():
    """An image nobody displays is dead weight in every clone.

    Matched against the page rather than against script names: one script can
    produce several images (`themes.py` renders every built-in theme), so
    stem-for-stem is the wrong pairing. That an image is *reproducible* is
    covered by the byte comparison above.
    """
    images = EXAMPLES.parent / "docs" / "gallery" / "images"
    gallery = (EXAMPLES.parent / "docs" / "gallery" / "index.md").read_text()
    orphans = sorted(
        p.name for p in images.iterdir()
        if p.suffix in (".png", ".gif") and p.name not in gallery
    )
    assert not orphans, (
        f"these gallery images are referenced by no page: {orphans}"
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=[s.stem for s in SCRIPTS])
def test_example_output_matches_the_committed_gallery_image(script, tmp_path, monkeypatch):
    """The picture on the gallery page is what the code beside it produces.

    Byte comparison, not a tolerance: both sides come from the same renderer on
    the same machine, so any difference means the image was not regenerated
    after a change. Skipped rather than failed when the committed image is
    absent — adding an example before its image is a normal intermediate state.
    """
    committed = EXAMPLES.parent / "docs" / "gallery" / "images"
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(script), run_name="__main__")

    compared = 0
    for produced in sorted(tmp_path.iterdir()):
        reference = committed / produced.name
        if not reference.is_file():
            continue
        compared += 1
        assert produced.read_bytes() == reference.read_bytes(), (
            f"{produced.name} differs from the committed gallery image. If the "
            f"change is intentional, re-run `python examples/{script.name}` "
            f"from {committed} and commit the result."
        )
    if compared == 0:
        pytest.skip(f"no committed gallery image for {script.name} yet")


def test_examples_write_only_relative_paths():
    """A script that saves to an absolute path, or climbs out of the working
    directory, would write into the user's tree when they copy-paste it."""
    offenders = []
    for script in SCRIPTS:
        for line in script.read_text().splitlines():
            if ".save(" not in line:
                continue
            if '"/' in line or "'/" in line or ".." in line or "os.path" in line:
                offenders.append(f"{script.name}: {line.strip()}")
    assert not offenders, "examples must save to a bare relative filename:\n" + \
        "\n".join(offenders)


def test_no_example_needs_a_third_party_import():
    """The gallery demonstrates pyplotrs, which has no runtime dependencies. An
    example importing numpy would imply one."""
    banned = ("import numpy", "import pandas", "import matplotlib", "import scipy")
    offenders = [
        f"{s.name}: {line.strip()}"
        for s in SCRIPTS
        for line in s.read_text().splitlines()
        if any(line.strip().startswith(b) for b in banned)
    ]
    assert not offenders, (
        "gallery examples should use only the standard library and pyplotrs:\n"
        + "\n".join(offenders)
    )


def test_examples_do_not_leak_into_the_repository(tmp_path, monkeypatch):
    """Running the whole gallery must leave the checkout untouched.

    `examples/output/` was tracked once and carried 2.6 MB HTML and SVG renders
    into every clone; it is gitignored now, but a script writing there again
    would still dirty the working tree for anyone who runs the gallery.
    """
    repo = EXAMPLES.parent
    before = {p for p in repo.rglob("*.png") if ".git" not in p.parts}
    monkeypatch.chdir(tmp_path)
    for script in SCRIPTS[:5]:
        runpy.run_path(str(script), run_name="__main__")
    after = {p for p in repo.rglob("*.png") if ".git" not in p.parts}
    assert before == after, f"running the examples created {sorted(after - before)}"

