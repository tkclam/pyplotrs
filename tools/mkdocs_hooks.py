"""MkDocs build hooks (declared under ``hooks:`` in ``mkdocs.yml``).

## Why a hook exists at all

The notebooks under ``docs/notebooks/`` link to each other the way a notebook
has to: ``[plot types](03_plot_types.ipynb)``, a plain relative path to the file
next door. That is the only spelling that works in the two places a notebook is
read outside this site — on GitHub, and in the reader's own Jupyter — and those
are not places a documentation URL would resolve.

MkDocs rewrites such links in ordinary Markdown pages, because it knows the
target is a page in the nav. It does not rewrite them inside a notebook, which
``mkdocs-jupyter`` hands over as already-rendered HTML. Left alone, every
cross-link in every notebook is a 404 on the site while being correct
everywhere else.

So the links stay written for the file system, and this rewrites them for the
site on the way out: one substitution, applied only to notebook pages.
"""

from __future__ import annotations

import re

#: `href="04_layout_and_composition.ipynb"` - a sibling notebook, by file name.
_SIBLING = re.compile(r'href="([0-9]{2}_[a-z0-9_]+)\.ipynb"')


def on_post_page(output: str, page, config) -> str:
    """Point notebook-to-notebook links at the rendered pages."""
    if not page.file.src_uri.startswith("notebooks/"):
        return output
    if not page.file.src_uri.endswith(".ipynb"):
        return output

    # With `use_directory_urls` (the default) a notebook renders to
    # `notebooks/<stem>/index.html`, so a sibling is one level up and one down.
    # With it off, pages are flat `notebooks/<stem>.html`.
    if config.get("use_directory_urls", True):
        replacement = r'href="../\1/"'
    else:
        replacement = r'href="\1.html"'
    return _SIBLING.sub(replacement, output)
