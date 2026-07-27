from __future__ import annotations

from app.config import DEFAULT_MODEL_ID, OPENROUTER_BASE_URL
from app.llm import build_llm


def test_build_llm_points_at_openrouter():
    llm = build_llm()
    assert llm.model_name == DEFAULT_MODEL_ID
    assert str(llm.openai_api_base).rstrip("/") == OPENROUTER_BASE_URL
    assert llm.streaming is True


def test_build_llm_honours_model_id_override(monkeypatch):
    from app import config

    monkeypatch.setenv("MODEL_ID", "some/other-model")
    config.get_settings.cache_clear()
    assert build_llm().model_name == "some/other-model"
