"""Server-side markdown rendering. The LLM writes from uncontrolled web pages,
so sanitising is not optional."""
from __future__ import annotations

import re

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
    # Remove dangerous tags outside code blocks (preserve content in fenced blocks)
    text_clean = _remove_dangerous_outside_fences(text)
    html = markdown_lib.markdown(text_clean, extensions=["extra", "sane_lists"])
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(clean, callbacks=[target_blank])


def _remove_dangerous_outside_fences(text: str) -> str:
    """Remove script/style tags outside markdown code fences."""
    parts: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        # Toggle fence state on triple backticks
        if line.strip().startswith("```"):
            in_fence = not in_fence
            parts.append(line)
        elif in_fence:
            # Preserve content inside code fences
            parts.append(line)
        else:
            # Remove dangerous tags outside fences
            line = re.sub(
                r"<(script|style).*?</\1>",
                "",
                line,
                flags=re.IGNORECASE | re.DOTALL,
            )
            parts.append(line)
    return "\n".join(parts)
