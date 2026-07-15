from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    """Convert an HTML fragment to readable plain text."""
    if not text:
        return ""
    # Greenhouse double-escapes its content field
    text = html.unescape(html.unescape(text))
    text = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _NL_RE.sub("\n\n", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …[truncated]"


def title_matches(title: str, keywords: list[str]) -> bool:
    """Case-insensitive substring pre-filter. Empty keyword list matches everything."""
    if not keywords:
        return True
    lowered = title.lower()
    return any(kw.lower() in lowered for kw in keywords)
