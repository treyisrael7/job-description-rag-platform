"""Prior-answer feedback normalization for adaptive question generation."""

from app.models import InterviewAnswer

def _feedback_line_from_item(x: object) -> str:
    """Normalize one strength or gap entry (string or {{text, ...}}) to a line of text."""
    if isinstance(x, dict):
        t = str(x.get("text", "")).strip()
        if t:
            return t
        return ""
    return str(x).strip() if x else ""


def _feedback_from_answer_row(answer: InterviewAnswer) -> dict[str, list[str]]:
    """Normalize strengths/gaps from stored answer columns and feedback_json."""
    strengths: list[str] = []
    gaps: list[str] = []
    if isinstance(answer.strengths, list):
        strengths = [_feedback_line_from_item(x) for x in answer.strengths if _feedback_line_from_item(x)]
    if isinstance(answer.weaknesses, list):
        gaps = [_feedback_line_from_item(x) for x in answer.weaknesses if _feedback_line_from_item(x)]
    fj = answer.feedback_json if isinstance(answer.feedback_json, dict) else {}
    if not strengths:
        s = fj.get("strengths")
        if isinstance(s, list):
            strengths = [_feedback_line_from_item(x) for x in s if _feedback_line_from_item(x)]
    if not gaps:
        g = fj.get("gaps")
        if isinstance(g, list):
            gaps = [_feedback_line_from_item(x) for x in g if _feedback_line_from_item(x)]
    return {"strengths": strengths, "gaps": gaps}


def _format_feedback_lines(items: list[str]) -> str:
    if not items:
        return "(none recorded)"
    return "; ".join(items)
