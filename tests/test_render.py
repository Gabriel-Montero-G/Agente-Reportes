from __future__ import annotations

from app.render import render_markdown


def test_renders_headings_and_lists():
    html = render_markdown("# Título\n\n- uno\n- dos")
    assert "<h1>Título</h1>" in html
    assert "<li>uno</li>" in html


def test_strips_script_tags():
    html = render_markdown("Hola <script>alert('xss')</script> mundo")
    # Script tag should be escaped/removed, not present as raw HTML tag
    assert "<script>" not in html
    # Surrounding text is preserved (bleach escapes/strips tags without deleting content)
    assert "Hola" in html
    assert "mundo" in html


def test_strips_event_handlers_and_javascript_urls():
    html = render_markdown('<a href="javascript:alert(1)" onclick="evil()">clic</a>')
    assert "javascript:" not in html
    assert "onclick" not in html


def test_keeps_http_links_and_opens_them_in_a_new_tab():
    html = render_markdown("[Fuente](https://example.com)")
    assert 'href="https://example.com"' in html
    assert 'target="_blank"' in html


def test_empty_input_renders_empty_string():
    assert render_markdown("") == ""


def test_code_blocks_with_script_tags_are_escaped_not_deleted():
    """Regression test: code blocks should quote script tags safely, not delete them."""
    # Test fenced code block
    html = render_markdown('```html\n<script>alert(1)</script>\n```')
    assert "alert" in html
    assert "1" in html
    assert "<pre>" in html or "<code>" in html
    assert "<script>" not in html

    # Test inline backticks (single-backtick span)
    html = render_markdown("Se encontró este código: `<script>alert(1)</script>` que es peligroso.")
    assert "alert" in html
    assert "1" in html
    assert "<code>" in html
    assert "<script>" not in html
