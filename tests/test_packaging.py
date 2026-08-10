"""The source distribution has to be buildable.

`139179d` vendored a patched krilla and wired it in with
``[patch.crates-io] krilla = { path = "vendor/krilla-0.8.2" }``, but did not add
``vendor/`` to ``[tool.maturin].include``. maturin does not follow patch paths
when collecting an sdist, so the resulting tarball carried the patch stanza and
none of the code it pointed at: ``cargo metadata`` on it died with ``failed to
load source for dependency krilla``. Wheels were fine - they build from the git
checkout, where ``vendor/`` is tracked - so nothing caught it. CI's ``sdist``
job only *built* the sdist and never built *from* it, and the sdist is exactly
what PyPI hands to any platform without a matching wheel.

Two tests, deliberately at different costs:

* :func:`test_patch_paths_are_included_in_sdist` is static and instant, so it
  runs in the normal suite and fails the moment a new ``[patch.crates-io]``
  path is added without an ``include`` entry.
* :func:`test_sdist_resolves` actually builds the tarball and resolves it with
  cargo. It needs maturin and a network-warm cargo registry, so it is marked
  ``packaging`` and deselected by default; CI runs it explicitly.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _patch_paths() -> list[str]:
    """Local paths the root workspace patches crates.io with."""
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())
    patched = cargo.get("patch", {}).get("crates-io", {})
    return [spec["path"] for spec in patched.values() if "path" in spec]


def _sdist_include_globs() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    include = pyproject.get("tool", {}).get("maturin", {}).get("include", [])
    return [e["path"] for e in include
            if isinstance(e, dict) and e.get("format") in (None, "sdist")]


def test_there_is_something_to_check():
    """Guard the guard: if the krilla patch is ever dropped, these tests would
    silently pass while asserting nothing."""
    assert _patch_paths(), "expected at least one [patch.crates-io] path entry"


@pytest.mark.parametrize("patch_path", _patch_paths())
def test_patch_paths_are_included_in_sdist(patch_path):
    """Every patched path must have its sources swept into the sdist.

    Checked by expanding the include globs for real rather than by comparing
    strings, so a glob that looks right but matches nothing still fails.
    """
    covered = {p.relative_to(ROOT) for glob in _sdist_include_globs()
               for p in ROOT.glob(glob) if p.is_file()}

    # The crate cannot be resolved without its manifest, nor built without its
    # sources; if both are in, the glob is sweeping the tree rather than a
    # single stray file.
    manifest = Path(patch_path) / "Cargo.toml"
    assert manifest in covered, (
        f"{manifest} is missing from the sdist: '{patch_path}' is a "
        f"[patch.crates-io] target, so cargo cannot resolve the dependency "
        f"graph without it. Add it to [tool.maturin].include in pyproject.toml."
    )
    sources = [p for p in covered
               if p.is_relative_to(Path(patch_path) / "src") and p.suffix == ".rs"]
    assert sources, f"no .rs sources from {patch_path}/src are in the sdist"


@pytest.mark.packaging
def test_sdist_resolves(tmp_path):
    """Build the sdist and resolve it with cargo, the way a from-source install
    does. This is the check whose absence let the broken sdist ship."""
    if shutil.which("cargo") is None:
        pytest.skip("cargo not available")

    out = tmp_path / "dist"
    build = subprocess.run(
        [sys.executable, "-m", "maturin", "sdist", "-o", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    if build.returncode != 0:
        if "No module named maturin" in build.stderr:
            pytest.skip("maturin not available")
        pytest.fail(f"maturin sdist failed:\n{build.stderr}")

    tarballs = list(out.glob("*.tar.gz"))
    assert len(tarballs) == 1, f"expected one sdist, got {tarballs}"

    extracted = tmp_path / "src"
    with tarfile.open(tarballs[0]) as tar:
        tar.extractall(extracted, filter="data")
    (pkg,) = list(extracted.iterdir())

    resolved = subprocess.run(
        ["cargo", "metadata", "--format-version", "1",
         "--manifest-path", str(pkg / "Cargo.toml")],
        capture_output=True, text=True,
    )
    assert resolved.returncode == 0, (
        "the sdist does not resolve - a from-source `pip install` would fail "
        f"here:\n{resolved.stderr}"
    )
