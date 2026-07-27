"""Server-side markdown rendering. The LLM writes from uncontrolled web pages,
so sanitising is not optional."""
from __future__ import annotations

import bleach
import markdown as markdown_lib
from bleach.callbacks import target_blank

ALLOWED_TAGS = frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr", "blockquote",
    "ul", "ol", "li",
    "strong", "em", "code", "pre",
    "a", "table", "thead", "tbody", "tr", "th", "td",
})
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}
ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto"})


def render_markdown(text: str) -> str:
    """Convert markdown to HTML that is safe to inject into the report panel."""
    if not text:
        return ""
    html = markdown_lib.markdown(text, extensions=["extra", "sane_lists"])
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=False,
    )
    return bleach.linkify(clean, callbacks=[target_blank])
