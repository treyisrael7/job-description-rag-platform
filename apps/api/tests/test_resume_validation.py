"""resume_validation heuristics (not too strict, reject obvious non-resumes)."""

import pytest

from app.services.resume_validation import validate_resume_text


def test_validate_resume_text_accepts_typical_resume():
    text = """
    Jane Doe
    jane.doe@email.com | (555) 123-4567 | linkedin.com/in/janedoe

    Professional summary
    Software engineer with 5 years of experience building web applications.

    Experience
    Senior Developer at Acme Corp: led migration to cloud infrastructure.

    Education
    Bachelor of Science in Computer Science, State University

    Skills
    Python, TypeScript, PostgreSQL, AWS
    """
    validate_resume_text(text)  # no raise


def test_validate_resume_text_rejects_too_short():
    with pytest.raises(ValueError, match="little text"):
        validate_resume_text("Hi")


def test_validate_resume_text_rejects_job_posting_like():
    text = """
    We are seeking a qualified candidate for our growing team.
    Responsibilities include leading projects and mentoring junior staff.
    Qualifications: Bachelor degree required. Benefits include health insurance.
    The company is an equal opportunity employer. Apply now for this exciting role.
    """ * 5
    with pytest.raises(ValueError, match="job posting"):
        validate_resume_text(text)


def test_validate_resume_text_rejects_unrelated_long_text():
    text = """
    Chapter One. The weather was fine. She walked down the street thinking about
    nothing in particular. Birds sang in the trees. The shop windows reflected clouds.
    """ * 40
    with pytest.raises(ValueError, match="doesn't look like a resume"):
        validate_resume_text(text)
