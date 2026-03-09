"""Heuristic-first comparison helpers for resume-to-JD gap analysis."""

import re
from typing import Any

from app.models import Document

STOPWORDS = {
    "and", "or", "the", "a", "an", "with", "for", "of", "to", "in", "on", "using",
    "experience", "knowledge", "ability", "skills", "skill", "required", "preferred",
}
EDUCATION_KEYWORDS = {
    "phd": "phd",
    "doctorate": "phd",
    "master": "master",
    "mba": "master",
    "bachelor": "bachelor",
    "associate": "associate",
}


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9#+.\s-]+", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _significant_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9#+.]+", value.lower())
    return [token for token in tokens if len(token) > 1 and token not in STOPWORDS]


def _parse_years(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\d+)\s*\+?\s*years?", value, re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _education_requirement_level(value: str | None) -> str | None:
    normalized = _normalize_text(value or "")
    for keyword, level in EDUCATION_KEYWORDS.items():
        if keyword in normalized:
            return level
    return None


def _canonical_target_id(kind: str, label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_text(label)).strip("-")
    return f"{kind}:{slug or 'item'}"


def build_requirement_targets(document: Document, max_targets: int = 18) -> list[dict]:
    """Build a deduplicated, typed target list from existing JD intelligence."""
    jd_struct = document.jd_extraction_json if isinstance(document.jd_extraction_json, dict) else {}
    role_profile = document.role_profile if isinstance(document.role_profile, dict) else {}
    competencies = document.competencies if isinstance(document.competencies, list) else []

    targets: dict[str, dict[str, Any]] = {}

    def add_target(
        *,
        kind: str,
        label: str,
        importance: str,
        description: str | None = None,
        jd_evidence: list[dict] | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        cleaned = label.strip()
        if not cleaned:
            return
        label_key = _normalize_text(cleaned)
        if kind in {"competency", "focus_area"}:
            for existing in targets.values():
                if _normalize_text(existing["label"]) == label_key:
                    if jd_evidence and not existing.get("jd_evidence"):
                        existing["jd_evidence"] = jd_evidence
                    return
        target_id = _canonical_target_id(kind, cleaned)
        if target_id in targets:
            existing = targets[target_id]
            if jd_evidence:
                existing["jd_evidence"] = existing.get("jd_evidence") or jd_evidence
            for alias in aliases or []:
                if alias and alias not in existing["aliases"]:
                    existing["aliases"].append(alias)
            return
        targets[target_id] = {
            "id": target_id,
            "type": kind,
            "label": cleaned,
            "importance": importance,
            "description": description,
            "aliases": [alias for alias in (aliases or []) if alias],
            "jd_evidence": jd_evidence or [],
        }

    for skill in jd_struct.get("required_skills") or []:
        add_target(kind="skill", label=str(skill), importance="required")
    for skill in jd_struct.get("preferred_skills") or []:
        add_target(kind="skill", label=str(skill), importance="preferred")
    for tool in jd_struct.get("tools") or []:
        add_target(kind="tool", label=str(tool), importance="required")
    for cloud in jd_struct.get("cloud_platforms") or []:
        add_target(kind="cloud", label=str(cloud), importance="required")

    if jd_struct.get("experience_years_required"):
        years_label = str(jd_struct["experience_years_required"])
        add_target(
            kind="experience",
            label=years_label,
            importance="required",
            aliases=[f"{_parse_years(years_label) or ''} years"],
        )
    if jd_struct.get("education_requirements"):
        add_target(
            kind="education",
            label=str(jd_struct["education_requirements"]),
            importance="required",
        )

    for competency in competencies:
        if not isinstance(competency, dict):
            continue
        add_target(
            kind="competency",
            label=str(competency.get("label", "")),
            importance="core",
            description=competency.get("description"),
            jd_evidence=competency.get("evidence") if isinstance(competency.get("evidence"), list) else [],
        )

    for focus_area in role_profile.get("focusAreas") or []:
        add_target(
            kind="focus_area",
            label=str(focus_area),
            importance="supporting",
        )

    ordered = list(targets.values())
    return ordered[:max_targets]


def build_resume_query(target: dict, helper_profiles: list[dict]) -> str:
    """Build a retrieval query for resume evidence, using helper cache only for expansion."""
    query_terms = [target["label"], *target.get("aliases", [])]
    target_norm = _normalize_text(target["label"])
    target_tokens = set(_significant_tokens(target["label"]))

    for profile in helper_profiles:
        if not isinstance(profile, dict):
            continue
        for bucket_name in ("skills", "tools", "cloudPlatforms", "education", "certifications"):
            for item in profile.get(bucket_name) or []:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label", "")).strip()
                if not label:
                    continue
                normalized = _normalize_text(label)
                label_tokens = set(_significant_tokens(label))
                if normalized == target_norm or (target_tokens and target_tokens.intersection(label_tokens)):
                    query_terms.append(label)

    deduped: list[str] = []
    seen: set[str] = set()
    for term in query_terms:
        normalized = _normalize_text(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(term)
    return " ".join(deduped)


def classify_requirement_match(target: dict, resume_evidence: list[dict]) -> dict:
    """Classify a single requirement using raw retrieved resume evidence as source of truth."""
    normalized_label = _normalize_text(target["label"])
    aliases = [_normalize_text(alias) for alias in target.get("aliases", []) if alias]
    label_tokens = set(_significant_tokens(target["label"]))
    evidence_text = " ".join(_normalize_text(item.get("snippet", "")) for item in resume_evidence)

    def contains_alias() -> bool:
        search_terms = [normalized_label, *aliases]
        return any(term and term in evidence_text for term in search_terms)

    if target["type"] == "experience":
        required_years = _parse_years(target["label"])
        observed_years = [
            int(match.group(1))
            for item in resume_evidence
            for match in re.finditer(r"(\d+)\s*\+?\s*years?", item.get("snippet", ""), re.IGNORECASE)
        ]
        max_years = max(observed_years) if observed_years else None
        if required_years is not None and max_years is not None and max_years >= required_years:
            status = "match"
            rationale = f"Resume evidence shows {max_years}+ years against a {required_years}+ year requirement."
        elif required_years is not None and max_years is not None and max_years > 0:
            status = "partial"
            rationale = f"Resume evidence shows {max_years}+ years, below the {required_years}+ year requirement."
        else:
            status = "gap"
            rationale = "No clear years-of-experience evidence was retrieved from the resume."
        return {
            "status": status,
            "reason": rationale,
            "confidence": "high" if max_years is not None else "medium",
        }

    if target["type"] == "education":
        required_level = _education_requirement_level(target["label"])
        matched_level = None
        for keyword, level in EDUCATION_KEYWORDS.items():
            if keyword in evidence_text:
                matched_level = level
                break
        if required_level and matched_level == required_level:
            status = "match"
            rationale = f"Resume evidence references the required {required_level}-level education."
        elif matched_level:
            status = "partial"
            rationale = "Resume includes education evidence, but the exact requested level is unclear."
        else:
            status = "gap"
            rationale = "No matching education evidence was retrieved from the resume."
        return {
            "status": status,
            "reason": rationale,
            "confidence": "medium",
        }

    exact_hit = contains_alias()
    token_hits = sum(1 for token in label_tokens if token in evidence_text)
    has_resume_evidence = bool(resume_evidence)

    if exact_hit:
        status = "match"
        rationale = f"Resume evidence explicitly mentions {target['label']}."
        confidence = "high"
    elif target["type"] in {"competency", "focus_area"} and token_hits >= 2 and has_resume_evidence:
        status = "match"
        rationale = "Resume evidence strongly overlaps with the competency language."
        confidence = "medium"
    elif has_resume_evidence and token_hits >= 1:
        status = "partial"
        rationale = "Resume evidence is related, but the exact requirement is not stated clearly."
        confidence = "medium"
    elif has_resume_evidence:
        status = "partial"
        rationale = "Some potentially relevant resume evidence was retrieved, but it is weakly aligned."
        confidence = "low"
    else:
        status = "gap"
        rationale = "No supporting resume evidence was retrieved for this requirement."
        confidence = "medium"

    return {
        "status": status,
        "reason": rationale,
        "confidence": confidence,
    }
