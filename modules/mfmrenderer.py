from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

_MFMPY_PATH = Path(__file__).resolve().parent / "mfmpy"
if str(_MFMPY_PATH) not in sys.path:
    sys.path.insert(0, str(_MFMPY_PATH))

from .mfmpy import mfmpy as mfm  # noqa: E402

MfmNode = dict[str, Any]

_COLOR_RE = re.compile(r"^[0-9a-f]{3,6}$", re.I)
_BORDER_STYLES = {
    "hidden",
    "dotted",
    "dashed",
    "solid",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
}


def _escape(value: object, quote_attr: bool = True) -> str:
    return html.escape(str(value), quote=quote_attr)


def _escape_text(value: str) -> str:
    escaped = _escape(value)
    return escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br />")


def _valid_href(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _safe_float(value: object, default: float) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_float(value: float) -> str:
    return f"{value:g}"


def _valid_color(value: object, default: str = "f00") -> str:
    if isinstance(value, str) and _COLOR_RE.match(value):
        return value
    return default


def _stringify(node: MfmNode | list[MfmNode]) -> str:
    try:
        return mfm.to_string(node)
    except Exception:
        if isinstance(node, list):
            return "".join(_stringify(child) for child in node)
        props = node.get("props") or {}
        if node.get("type") == "text":
            return str(props.get("text", ""))
        return ""


def _ruby(children: list[MfmNode], render_children: Callable[[list[MfmNode]], str]) -> str:
    if len(children) == 1:
        child = children[0]
        text = child.get("props", {}).get("text", "") if child.get("type") == "text" else ""
        base, _, rt = text.partition(" ")
        return f"<ruby>{_escape(base)}<rp>(</rp><rt>{_escape(rt)}</rt><rp>)</rp></ruby>"

    rt_node = children[-1] if children else None
    if rt_node is None:
        return ""

    rt = rt_node.get("props", {}).get("text", "") if rt_node.get("type") == "text" else ""
    base = render_children(children[:-1])
    return f"<ruby>{base}<rp>(</rp><rt>{_escape(rt.strip())}</rt><rp>)</rp></ruby>"


def _mfm_span(classes: list[str], children: str, style: str = "") -> str:
    class_attr = _escape(" ".join(["mfm-fn", *classes]))
    style_attr = f' style="{_escape(style)}"' if style else ""
    return f'<span class="{class_attr}"{style_attr}>{children}</span>'


def _render_fn(
    props: dict[str, Any],
    children: list[MfmNode],
    render_children: Callable[[list[MfmNode]], str],
) -> str | None:
    name = props.get("name")
    args = props.get("args") or {}
    rendered = render_children(children)

    if name == "ruby":
        return _ruby(children, render_children)

    if name == "rotate":
        degrees = _safe_float(args.get("deg"), 90)
        return _mfm_span(
            ["mfm-rotate"],
            rendered,
            f"transform: rotate({_format_float(degrees)}deg);",
        )

    if name == "position":
        x = _safe_float(args.get("x"), 0)
        y = _safe_float(args.get("y"), 0)
        return _mfm_span(
            ["mfm-position"],
            rendered,
            f"transform: translateX({_format_float(x)}em) translateY({_format_float(y)}em);",
        )

    if name == "scale":
        x = min(_safe_float(args.get("x"), 1), 5)
        y = min(_safe_float(args.get("y"), 1), 5)
        return _mfm_span(
            ["mfm-scale"],
            rendered,
            f"transform: scale({_format_float(x)}, {_format_float(y)});",
        )

    if name == "fg":
        color = _valid_color(args.get("color"))
        return _mfm_span(["mfm-fg"], rendered, f"color: #{color};")

    if name == "bg":
        color = _valid_color(args.get("color"))
        return _mfm_span(["mfm-bg"], rendered, f"background-color: #{color};")

    if name == "border":
        color = _valid_color(args.get("color"), "currentColor")
        color_value = color if color == "currentColor" else f"#{color}"
        border_style = args.get("style")
        if not isinstance(border_style, str) or border_style not in _BORDER_STYLES:
            border_style = "solid"
        width = _safe_float(args.get("width"), 1)
        radius = _safe_float(args.get("radius"), 0)
        classes = ["mfm-border"]
        if not args.get("noclip"):
            classes.append("mfm-border-clip")
        return _mfm_span(
            classes,
            rendered,
            (
                f"border: {_format_float(width)}px {border_style} {color_value}; "
                f"border-radius: {_format_float(radius)}px;"
            ),
        )

    return None


def toHtml(
    text: str | None,
    *,
    emojiStore: Any = None,
    emojiUrlFilter: Callable[[str], str] | None = None,
    unicodeEmojiFilter: Callable[[str], str] | None = None,
    author_host: str | None = None,
    hashtag_url: str = "/search?type=tags&q=",
    profile_url: str = "/@",
) -> str:
    if not text:
        return ""

    try:
        nodes = mfm.parse(text)
    except Exception:
        return _escape_text(text)

    def render_children(children: list[MfmNode] | None) -> str:
        if children is None:
            return ""
        return "".join(render_node(child) for child in children)

    def render_node(node: MfmNode) -> str:
        node_type = node.get("type")
        props = node.get("props") or {}
        children = node.get("children") or []

        if node_type == "bold":
            return f"<b>{render_children(children)}</b>"

        if node_type == "small":
            return f"<small>{render_children(children)}</small>"

        if node_type == "strike":
            return f"<del>{render_children(children)}</del>"

        if node_type == "italic":
            return f"<i>{render_children(children)}</i>"

        if node_type == "fn":
            rendered_fn = _render_fn(props, children, render_children)
            if rendered_fn is not None:
                return rendered_fn
            return _escape_text(_stringify(node))

        if node_type == "blockCode":
            return f'<pre class="mfm-block-code"><code>{_escape(props.get("code", ""))}</code></pre>'

        if node_type == "center":
            return f'<div class="mfm-center">{render_children(children)}</div>'

        if node_type == "emojiCode":
            name = str(props.get("name", ""))
            if emojiStore is not None and emojiUrlFilter is not None and author_host:
                try:
                    emoji = emojiStore.get(author_host, name)
                except Exception:
                    emoji = None
                if emoji:
                    src = _escape(emojiUrlFilter(emoji["url"]))
                    return f'<img loading="lazy" src="{src}" class="emoji-in-text">'
            return f":{_escape(name)}:"

        if node_type == "unicodeEmoji":
            emoji = str(props.get("emoji", ""))
            if unicodeEmojiFilter is not None:
                return unicodeEmojiFilter(emoji)
            return _escape(emoji)

        if node_type == "hashtag":
            hashtag = str(props.get("hashtag", ""))
            href = f"{hashtag_url}{quote(hashtag)}"
            return f'<a href="{_escape(href)}">#{_escape(hashtag)}</a>'

        if node_type == "link":
            url = str(props.get("url", ""))
            label = render_children(children)
            if _valid_href(url):
                return f'<a href="{_escape(url)}">{label}</a>'
            return _escape_text(_stringify(node))

        if node_type == "mention":
            acct = str(props.get("acct", ""))
            href = f"{profile_url}{quote(acct[1:] if acct.startswith('@') else acct, safe='@._-')}"
            return f'<a href="{_escape(href)}">{_escape(acct)}</a>'

        if node_type == "quote":
            return f'<blockquote class="mfm-quote">{render_children(children)}</blockquote>'

        if node_type == "text":
            return _escape_text(str(props.get("text", "")))

        if node_type == "url":
            url = str(props.get("url", ""))
            if _valid_href(url):
                return f'<a href="{_escape(url)}">{_escape(url)}</a>'
            return _escape(url)

        if node_type == "search":
            query = str(props.get("query", ""))
            content = str(props.get("content", ""))
            href = f"https://www.google.com/search?q={quote(query)}"
            return f'<a href="{_escape(href)}">{_escape(content)}</a>'

        if node_type == "plain":
            return _escape_text(_stringify(children))

        return _escape_text(_stringify(node))

    return render_children(nodes)
