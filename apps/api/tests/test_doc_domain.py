"""Tests for doc_domain detection."""

import pytest

from app.services.doc_domain import detect_doc_domain, normalize_section_type


def test_detect_job_description_two_signals():
    """Text with >=2 job description signals detected as job_description."""
    text = """
    Key Responsibilities
    Design ML pipelines. Build models.
    Qualifications
    5+ years experience. Bachelor's degree.
    """
    assert detect_doc_domain(text) == "job_description"


def test_detect_job_description_many_signals():
    """Text with many job description signals detected as job_description."""
    text = """
    About the Role
    We seek an AI Engineer.
    Position Summary
    Build ML solutions.
    Key Responsibilities
    Design pipelines.
    Qualifications
    Required: Python. Preferred: PhD.
    Salary: $100k - $150k.
    """
    assert detect_doc_domain(text) == "job_description"


def test_detect_general_one_signal():
    """Text with only 1 job description signal -> general."""
    text = """
    Project Report
    Responsibilities: We delivered the project on time.
    Methodology and results follow.
    """
    assert detect_doc_domain(text) == "general"


def test_detect_general_no_signals():
    """Plain document without job description signals -> general."""
    text = """
    Quarterly Financial Report
    Revenue increased 15%. Operating expenses were in line.
    The board approved the dividend.
    """
    assert detect_doc_domain(text) == "general"


def test_detect_general_short_text():
    """Very short text -> general."""
    assert detect_doc_domain("Hi") == "general"
    assert detect_doc_domain("") == "general"


def test_normalize_section_type_canonical():
    """Map job description section names to canonical 6 types."""
    assert normalize_section_type("responsibilities") == "responsibilities"
    assert normalize_section_type("qualifications") == "qualifications"
    assert normalize_section_type("preferred_qualifications") == "qualifications"
    assert normalize_section_type("tools_technologies") == "tools"
    assert normalize_section_type("compensation") == "compensation"
    assert normalize_section_type("about") == "about"
    assert normalize_section_type("position_summary") == "about"
    assert normalize_section_type("location") == "other"
    assert normalize_section_type("company_info") == "other"


def test_normalize_section_type_unknown():
    """Unknown section -> other."""
    assert normalize_section_type("unknown") == "other"
    assert normalize_section_type(None) == "other"
    assert normalize_section_type("") == "other"
