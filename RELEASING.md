# Releasing pyplotrs

The version lives in **one** place: `[workspace.package].version` in
`Cargo.toml`. `pyproject.toml` takes it via `dynamic = ["version"]`, and
`pyplotrs.__version__` reads it back out of the installed metadata.

## One-time setup

1. **PyPI Trusted Publisher.** At
   <https://pypi.org/manage/account/publishing/>, add a publisher for project
   `pyplotrs`, owner `tkclam`, repository `pyplotrs`, workflow `CI.yml`,
   environment `pypi`. There is no API token to create — that is the point.
2. **The `pypi` environment.** In repository Settings → Environments, create
   `pypi` and add required reviewers if you want a human gate on uploads.
3. **Branch protection on `main`,** requiring these checks:
   `tests, lint and docs`, `minimum supported Rust version`,
   `linux (x86_64)`, `windows (x64)`, `macos (aarch64)`, `sdist`.
4. **GitHub Pages** set to deploy from GitHub Actions.

## Cutting a release

1. **Green locally.** Everything in `CONTRIBUTING.md`'s gate, plus the two
   slow ones:

   ```bash
   pytest -q --strict-markers -m packaging
   python benchmarks/matrix.py            # regenerates benchmarks/RESULTS.md
   ```

2. **Bump the version** in `Cargo.toml` (`[workspace.package].version`) and
   run `cargo check --workspace` so `Cargo.lock` picks it up. Then bump
   `version` and `date-released` in `CITATION.cff` to match — GitHub's "Cite
   this repository" widget reads them verbatim, and CFF has no way to take
   them from the build. Nothing else states a version; if you find something
   that does, that is a bug.

3. **Cut the changelog.** In `docs/about/changelog.md`, rename `## Unreleased`
   to `## X.Y.Z — YYYY-MM-DD` and open a fresh empty `## Unreleased` above it.
   Read the section as a user would: it describes what changed for *them*, not
   what happened in the repository.

4. **Regenerate the notices** if any dependency moved:

   ```bash
   python tools/gen_third_party_notices.py
   ```

5. **Commit and push to `main`.** Wait for CI, and for the docs deploy — the
   README links to `tkclam.github.io/pyplotrs`, so a release with a broken
   docs build ships broken links.

6. **Tag and push the tag.**

   ```bash
   git tag -s v0.1.0 -m "pyplotrs 0.1.0"
   git push origin v0.1.0
   ```

   The tag pattern is `v[0-9]+.[0-9]+.[0-9]+`; anything else does not trigger
   a release. The `release` job asserts the tag matches the package version and
   that a matching wheel exists **before** uploading, because a wrong version
   on PyPI can be yanked but never replaced.

7. **Verify the upload.** Open <https://pypi.org/project/pyplotrs/> and click
   Homepage, Documentation, Issues and Changelog. Confirm the README renders
   with its images. Then, on a machine with no Rust toolchain:

   ```bash
   python -m venv /tmp/v && /tmp/v/bin/pip install pyplotrs
   /tmp/v/bin/python -c "import pyplotrs; print(pyplotrs.__version__)"
   ```

   `pip` must serve a **wheel**, not the sdist — if it builds from source, the
   wheel matrix did not cover that platform.

## If something goes wrong

- **Wrong version uploaded.** It cannot be replaced. Yank it on PyPI, fix the
  version, and release the next patch number.
- **A wheel is missing for a platform.** The sdist covers it, slowly. Fix the
  matrix and release a patch; do not delete the release.
- **The tag was wrong.** Delete it locally and remotely *before* the release
  job finishes. After it publishes, only step 1 above applies.
