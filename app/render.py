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


def _harden_link(
    attrs: dict[tuple[str | None, str] | str, str], new: bool = False
) -> dict[tuple[str | None, str] | str, str]:
    """Set target="_blank" (via bleach's default callback) and pair it with
    rel="noopener noreferrer" to prevent reverse tabnabbing: the report's
    "Fuentes" section links to arbitrary, untrusted pages scraped from web
    search, and a hostile page opened via target="_blank" without rel could
    otherwise rewrite this tab's location via window.opener.

    `attrs` keys are bleach's `(namespace, name)` tuples for HTML attributes
    (e.g. ``(None, "target")``), plus a special ``"_text"`` string key for the
    link's visible text; values are always strings."""
    attrs = target_blank(attrs, new)
    if (None, "target") in attrs:
        attrs[(None, "rel")] = "noopener noreferrer"
    return attrs


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
    return bleach.linkify(clean, callbacks=[_harden_link])
