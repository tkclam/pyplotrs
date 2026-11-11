"""Rich text: style part of a label.

Anywhere a label is accepted (titles, axis and tick labels, legend entries,
``Axes.text``) a rich-text span works too::

    ax.set(title=pp.rich("Growth ", pp.bold("+42%", color="C3"), " in 6 months"))

Helpers nest, and inner styles win. Style keys: ``weight`` ("normal"/"bold"),
``style`` ("normal"/"italic"), ``color``, ``bgcolor`` (highlight), ``underline``,
``strike``, and ``scale`` (relative to the label's size) or ``size`` (points).

Labels may contain ``$...$`` math. Inside math, ``\\textcolor{C1}{x}`` tints a
term.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

__all__ = ["Span", "bold", "italic", "mark", "plain", "rich", "strike", "underline"]

_STYLE_KEYS = frozenset(
    {"weight", "style", "color", "bgcolor", "underline", "strike", "size", "scale"}
)
_HIGHLIGHT = "#ffe89a"


@dataclass(frozen=True)
class Span:
    """Text plus the style to draw it in. Build with `rich` and friends."""

    parts: tuple[Any, ...]
    style: Mapping[str, Any]

    def __post_init__(self) -> None:
        unknown = set(self.style) - _STYLE_KEYS
        if unknown:
            raise TypeError(
                f"unknown text style {sorted(unknown)}; expected any of {sorted(_STYLE_KEYS)}"
            )
        if "size" in self.style and "scale" in self.style:
            raise TypeError("pass size= (points) or scale= (relative), not both")

    @property
    def text(self) -> str:
        """The plain characters, without styling."""
        return "".join(t for t, _ in flatten(self))

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        args = [repr(p) for p in self.parts] + [f"{k}={v!r}" for k, v in sorted(self.style.items())]
        return f"rich({', '.join(args)})"


Label = str | Span


def rich(*parts: Any, **style: Any) -> Span:
    """A span of strings and nested spans, all in ``style``."""
    return Span(tuple(parts), MappingProxyType(dict(style)))


def bold(*parts: Any, **style: Any) -> Span:
    return rich(*parts, **{"weight": "bold", **style})


def italic(*parts: Any, **style: Any) -> Span:
    return rich(*parts, **{"style": "italic", **style})


def underline(*parts: Any, **style: Any) -> Span:
    return rich(*parts, **{"underline": True, **style})


def strike(*parts: Any, **style: Any) -> Span:
    return rich(*parts, **{"strike": True, **style})


def mark(*parts: Any, **style: Any) -> Span:
    """Highlighted text, drawn over a ``bgcolor`` panel (pale yellow by default)."""
    return rich(*parts, **{"bgcolor": _HIGHLIGHT, **style})


def plain(s: Any) -> str:
    """The unstyled text of a label."""
    return s.text if isinstance(s, Span) else str(s)


def as_label(s: Any) -> Label:
    """A user-supplied label: spans pass through, anything else becomes ``str``."""
    return s if isinstance(s, Span) else str(s)


def flatten(obj: Any, base: Mapping[str, Any] | None = None) -> list[tuple[str, dict]]:
    """Leaves of a rich-text tree as ``(text, style)``, merging neighbors that
    share a style so they shape (and kern) as one run."""
    leaves: list[tuple[str, dict]] = []

    def walk(node: Any, style: dict) -> None:
        if isinstance(node, Span):
            inner = {**style, **node.style}
            for p in node.parts:
                walk(p, inner)
        elif isinstance(node, (list, tuple)):
            for p in node:
                walk(p, style)
        elif s := str(node):
            if leaves and leaves[-1][1] == style:
                leaves[-1] = (leaves[-1][0] + s, style)
            else:
                leaves.append((s, style))

    walk(obj, dict(base or {}))
    return leaves
