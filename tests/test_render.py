from __future__ import annotations

from app.render import render_markdown


def test_renders_headings_and_lists():
    html = render_markdown("# Título\n\n- uno\n- dos")
    assert "<h1>Título</h1>" in html
    assert "<li>uno</li>" in html


def test_strips_script_tags():
    html = render_markdown("Hola <script>alert('xss')</script> mundo")
    assert "<script>" not in html
    assert "alert" not in html


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
