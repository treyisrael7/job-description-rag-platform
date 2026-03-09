"""Deterministic explanation helpers for resume-to-JD gap analysis."""


def _citation_from_evidence(item: dict) -> dict:
    return {
        "chunkId": str(item.get("chunkId", "")),
        "page": item.get("page"),
        "sourceTitle": str(item.get("sourceTitle", "")),
        "sourceType": str(item.get("sourceType", "")),
    }


def summarize_gap_analysis(results: list[dict]) -> dict:
    """Build summary metrics plus cited strengths/gaps from compared targets."""
    if not results:
        return {
            "summary": "No comparison results were produced.",
            "overall_alignment_score": 0,
            "strengths_cited": [],
            "gaps_cited": [],
        }

    weights = {"required": 3, "core": 3, "preferred": 2, "supporting": 1}
    scores = {"match": 1.0, "partial": 0.5, "gap": 0.0, "unknown": 0.0}

    total_weight = 0
    earned_weight = 0.0
    strengths_cited = []
    gaps_cited = []

    for item in results:
        weight = weights.get(item.get("importance", "supporting"), 1)
        total_weight += weight
        earned_weight += weight * scores.get(item.get("status", "gap"), 0.0)

        resume_citations = [
            _citation_from_evidence(evidence)
            for evidence in item.get("resume_evidence") or []
            if evidence.get("chunkId")
        ]
        jd_citations = [
            _citation_from_evidence(evidence)
            for evidence in item.get("jd_evidence") or []
            if evidence.get("chunkId")
        ]

        if item.get("status") == "match":
            strengths_cited.append(
                {
                    "text": f"{item['label']}: {item['reason']}",
                    "citations": resume_citations[:2] or jd_citations[:1],
                }
            )
        elif item.get("status") in {"partial", "gap"}:
            gaps_cited.append(
                {
                    "text": f"{item['label']}: {item['reason']}",
                    "citations": resume_citations[:2] or jd_citations[:1],
                }
            )

    alignment_score = round((earned_weight / total_weight) * 100) if total_weight else 0
    matched = sum(1 for item in results if item.get("status") == "match")
    partial = sum(1 for item in results if item.get("status") == "partial")
    gaps = sum(1 for item in results if item.get("status") == "gap")

    summary = (
        f"Alignment score {alignment_score}. "
        f"Matched {matched} requirements, partially matched {partial}, and found {gaps} clear gaps."
    )

    return {
        "summary": summary,
        "overall_alignment_score": alignment_score,
        "strengths_cited": strengths_cited[:5],
        "gaps_cited": gaps_cited[:5],
    }
