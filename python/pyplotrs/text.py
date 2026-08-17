"""Rich text: styling a *substring* of a label.

Every place pyplotrs takes a label - titles, axis labels, tick labels, legend
entries, ``Axes.text``/``annotate`` - also takes a rich-text object built from
the helpers here, so one word can be bold, tinted, highlighted or struck
through while the rest of the line is not::

    import pyplotrs as pp

    ax.set(title=pp.rich("Growth ", pp.bold("+42%", color="teal"),
                         " over ", pp.italic("6 months")))

The helpers nest, and an inner style wins over an outer one::

    pp.bold("total ", pp.rich("(estimated)", weight="normal", color="#888"))

**Styles.** ``weight`` (``"normal"``/``"bold"``), ``style``
(``"normal"``/``"italic"``), ``color``, ``bgcolor`` (a highlight panel behind
the run), ``underline``, ``strike``, and either ``scale`` (a multiple of the
label's own type size - usually what you want, since a title and a tick label
are set at different sizes) or ``size`` (absolute points). Colors accept
everything [`pyplotrs.theme.parse_color`][pyplotrs.theme.parse_color] does,
``"C0"`` palette indices included, and are resolved against the figure's theme
at draw time.

**Math.** A span may contain ``$...$``; the span's weight and slant become the
*ambient* face the math is set in, so ``pp.bold(r"$E = mc^2$")`` comes out bold
throughout - variables included - rather than half-bold. Inside a single
expression, use ``\\textcolor{...}{...}`` and ``\\colorbox{...}{...}`` to tint
one term::

    ax.set(xlabel=r"$\\textcolor{C1}{\\sigma} / \\sqrt{N}$")

**Kerning.** Each run is shaped independently, so a kern pair that straddles a
style boundary is lost - ``pp.rich("W", pp.bold("a"))`` sets a hair wider than
``"Wa"``. That is inherent to changing face mid-word and matches every other
plotting library; it does not apply within a run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from . import theme as _theme

__all__ = [
    "Span",
    "as_label",
    "bold",
    "flatten",
    "italic",
    "mark",
    "plain",
    "rich",
    "strike",
    "underline",
]

#: Every style key a span understands. Anything else is a typo, and is rejected
#: at construction rather than silently ignored at draw time - a misspelled
#: ``colour=`` that quietly did nothing would be found only by looking hard at
#: the finished figure.
_STYLE_KEYS = frozenset({
    "weight", "style", "color", "bgcolor", "underline", "strike", "size", "scale",
})

#: The default highlight, a soft marker-pen yellow. Light-on-dark themes will
#: want their own ``bgcolor``; there is no theme-independent highlight that
#: works on both a white and a near-black page.
_MARK_COLOR = "#ffe89a"


@dataclass(frozen=True)
class Span:
    """A run of text plus the style to draw it in, and the node type every
    rich-text helper returns.

    Build these with [`rich`][pyplotrs.text.rich] and its shorthands rather
    than directly. ``parts`` may hold plain strings and further ``Span``s, so a
    span is a tree; ``style`` applies to everything under it that does not
    override the same key.
    """

    parts: tuple[Any, ...]
    style: Mapping[str, Any]

    def __post_init__(self) -> None:
        unknown = set(self.style) - _STYLE_KEYS
        if unknown:
            raise TypeError(
                f"unknown text style {', '.join(map(repr, sorted(unknown)))}; "
                f"expected any of {', '.join(sorted(_STYLE_KEYS))}"
            )
        if "size" in self.style and "scale" in self.style:
            raise TypeError(
                "pass either size= (absolute points) or scale= (a multiple of "
                "the label's own size), not both"
            )

    @property
    def text(self) -> str:
        """The plain text of this span and everything under it, unstyled.

        This is what a figure's accessible description, ``get_title()`` and
        anything else that needs characters rather than glyphs should use.
        """
        return "".join(t for t, _ in flatten(self))

    def __str__(self) -> str:
        # So a stray `str(...)` degrades to the readable text rather than to a
        # repr full of nested constructors.
        return self.text

    def __repr__(self) -> str:
        args = [repr(p) for p in self.parts]
        args += [f"{k}={v!r}" for k, v in sorted(self.style.items())]
        return f"rich({', '.join(args)})"


def rich(*parts: Any, **style: Any) -> Span:
    """A styled span of ``parts`` (strings and/or nested spans).

    With no ``style`` it is a plain container, which is how you concatenate
    differently-styled pieces into one label::

        pp.rich("mean ", pp.bold("12.4"), " ± 0.3")

    See the module docstring for the style keys.
    """
    return Span(tuple(parts), MappingProxyType(dict(style)))


def bold(*parts: Any, **style: Any) -> Span:
    """``rich(...)`` in the body family's real bold face (not a synthetic one)."""
    return rich(*parts, **{"weight": "bold", **style})


def italic(*parts: Any, **style: Any) -> Span:
    """``rich(...)`` in the body family's real italic face."""
    return rich(*parts, **{"style": "italic", **style})


def underline(*parts: Any, **style: Any) -> Span:
    """``rich(...)`` underlined, on the rule the face's own metrics specify."""
    return rich(*parts, **{"underline": True, **style})


def strike(*parts: Any, **style: Any) -> Span:
    """``rich(...)`` struck through, on the rule the face's own metrics specify."""
    return rich(*parts, **{"strike": True, **style})


def mark(*parts: Any, **style: Any) -> Span:
    """``rich(...)`` highlighted - drawn over a panel of ``bgcolor``.

    Pass ``bgcolor=`` to change the panel; ``color=`` still means the ink, as
    it does on every other helper. A dark page wants both::

        pp.mark("peak", bgcolor="#22303f", color="#e6f0ff")

    The panel spans the whole line's height, not each run's own ink, so several
    marks in one label line up instead of stepping up and down with their
    letters.
    """
    return rich(*parts, **{"bgcolor": _MARK_COLOR, **style})


def plain(s: Any) -> str:
    """The unstyled text of ``s``, whether it is a ``Span`` or already a string.

    Use it wherever characters are wanted rather than glyphs - alt text, a
    filename, a dict key.
    """
    return s.text if isinstance(s, Span) else str(s)


def as_label(s: Any) -> Any:
    """``s`` untouched if it is rich text, otherwise coerced with ``str``.

    The coercion is what lets a label be given as a number or a
    ``pathlib.Path``; the exemption is what stops it flattening a ``Span`` into
    its repr. Use this instead of a bare ``str(...)`` anywhere a user-supplied
    label is stored.
    """
    return s if isinstance(s, Span) else str(s)


def flatten(obj: Any, base: Mapping[str, Any] | None = None) -> list[tuple[str, dict]]:
    """Walk a rich-text tree into a flat list of ``(text, style)`` leaves.

    An inner style overrides an outer one key by key. Adjacent leaves that end
    up with identical styles are merged into one, so ``rich("a", "b")`` shapes
    as a single kerned run rather than two - style boundaries should cost
    kerning only where the style actually changes.
    """
    out: list[tuple[str, dict]] = []

    def walk(node: Any, style: dict) -> None:
        if isinstance(node, Span):
            merged = {**style, **node.style}
            for p in node.parts:
                walk(p, merged)
        elif isinstance(node, (list, tuple)):
            for p in node:
                walk(p, style)
        else:
            s = node if isinstance(node, str) else str(node)
            if s:
                out.append((s, style))

    walk(obj, dict(base or {}))

    merged: list[tuple[str, dict]] = []
    for text, style in out:
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


# -- color specs inside a math span -----------------------------------------

#: `\textcolor{spec}{...}` / `\colorbox{spec}{...}`, capturing the spec. The
#: inner `[^{}]*` is deliberate: a color spec never contains braces, so this
#: cannot run past its own argument into the content that follows.
_MATH_COLOR = re.compile(r"\\(textcolor|colorbox)\{([^{}]*)\}")


def resolve_math_colors(s: Any, theme=None) -> str:
    """Rewrite every ``\\textcolor``/``\\colorbox`` spec in ``s`` to plain hex.

    The typesetter understands only ``#rrggbb``, on purpose: ``"C1"`` means
    *this theme's* second palette color and CSS names are a table Python
    already owns, so resolving here keeps one answer to "what color is that"
    instead of two that can drift. An unresolvable spec is left exactly as it
    was, and the typesetter then draws the term in the ambient color - a typo
    should cost a color, never a term of an equation.

    Every label passes through here on its way to being measured or drawn, so
    this is also where a label that is not a string becomes one - a tick label
    given as a number, a category given as a ``Path``. Doing it here rather
    than at each of the call sites that accept a label means they cannot
    disagree, and that measuring and drawing coerce identically.
    """
    if not isinstance(s, str):
        s = str(s)
    if "\\textcolor" not in s and "\\colorbox" not in s:
        return s
    t = _theme.get(theme)

    def sub(m: re.Match) -> str:
        try:
            r, g, b, a = t.resolve(m.group(2))
        except (ValueError, IndexError, TypeError):
            return m.group(0)
        return f"\\{m.group(1)}{{#{r:02x}{g:02x}{b:02x}{a:02x}}}"

    return _MATH_COLOR.sub(sub, s)
