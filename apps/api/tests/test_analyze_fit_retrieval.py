"""Education signal detection for analyze-fit chunk augmentation."""

import uuid

from app.services.analyze_fit_retrieval import resume_chunks_have_education_signal


def test_resume_education_detects_bachelor_and_university():
    rid = uuid.uuid4()
    assert resume_chunks_have_education_signal(
        [
            {
                "document_id": str(rid),
                "snippet": "Clemson University, Bachelor of Computer Science, Minor in Financial Management",
            }
        ],
        rid,
    )


def test_resume_education_false_for_skills_only():
    rid = uuid.uuid4()
    assert not resume_chunks_have_education_signal(
        [
            {
                "document_id": str(rid),
                "snippet": "Built microservices with Python and PostgreSQL.",
            }
        ],
        rid,
    )


def test_resume_education_ignores_jd_chunks():
    rid = uuid.uuid4()
    jd = uuid.uuid4()
    assert not resume_chunks_have_education_signal(
        [
            {
                "document_id": str(jd),
                "snippet": "Bachelor's degree required for this role.",
            }
        ],
        rid,
    )
