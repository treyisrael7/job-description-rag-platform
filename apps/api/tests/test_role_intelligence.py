"""Tests for Role Intelligence service."""

import pytest

from app.services.role_intelligence import (
    DEFAULT_PROFILE,
    infer_role_profile,
    VALID_DOMAINS,
    VALID_SENIORITIES,
)


def test_default_profile_structure():
    """Default profile has required keys and valid values."""
    assert DEFAULT_PROFILE["domain"] == "general_business"
    assert DEFAULT_PROFILE["seniority"] == "entry"
    assert DEFAULT_PROFILE["domain"] in VALID_DOMAINS
    assert DEFAULT_PROFILE["seniority"] in VALID_SENIORITIES
    qm = DEFAULT_PROFILE["questionMix"]
    assert qm["behavioral"] + qm["roleSpecific"] + qm["scenario"] == 100


def test_infer_empty_text_returns_default():
    """Short/empty text returns default profile."""
    result = infer_role_profile("")
    assert result["domain"] == "general_business"
    assert result["seniority"] == "entry"
    assert result["focusAreas"] == ["communication", "problem solving"]
    assert result["questionMix"]["behavioral"] + result["questionMix"]["roleSpecific"] + result["questionMix"]["scenario"] == 100


def test_infer_short_text_returns_default():
    """Text under 50 chars returns default."""
    result = infer_role_profile("Short")
    assert result["domain"] == "general_business"


def test_infer_returns_valid_domain_and_seniority(monkeypatch):
    """Inference returns domain/seniority within valid sets (or default on API failure)."""
    monkeypatch.setattr("app.services.role_intelligence.settings.openai_api_key", None)
    result = infer_role_profile("A" * 100)
    assert result["domain"] in VALID_DOMAINS
    assert result["seniority"] in VALID_SENIORITIES
