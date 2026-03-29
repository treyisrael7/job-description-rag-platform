"use client";

import type { RubricScoreItem } from "@/lib/api";

/** Normalize API / stored evaluation_json shapes for display. */
export function normalizeRubricScoresForDisplay(raw: unknown): RubricScoreItem[] {
  if (!Array.isArray(raw)) return [];
  const out: RubricScoreItem[] = [];
  for (const item of raw) {
    if (item == null || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const name = String(o.name ?? "").trim();
    if (!name) continue;
    const score =
      typeof o.score === "number" && !Number.isNaN(o.score)
        ? o.score
        : Number(o.score);
    const reasoning = String(o.reasoning ?? "").trim();
    out.push({
      name,
      score: Number.isFinite(score) ? Math.max(0, Math.min(10, score)) : 0,
      reasoning,
    });
  }
  return out;
}

function formatScoreTen(score: number): string {
  const clamped = Math.max(0, Math.min(10, score));
  const r = Math.round(clamped * 10) / 10;
  return Number.isInteger(r) ? String(r) : r.toFixed(1);
}

function scoreColorClass(score: number): string {
  if (score >= 8) return "text-emerald-700";
  if (score >= 6) return "text-amber-700";
  return "text-red-700";
}

interface RubricDimensionScoresProps {
  items: RubricScoreItem[];
  /** Screen-reader heading (visual title is optional via children) */
  heading?: string;
  className?: string;
}

/**
 * Lists role-specific dimension scores as Name: x/10 with expandable reasoning per row.
 */
export function RubricDimensionScores({
  items,
  heading = "Dimension scores",
  className = "",
}: RubricDimensionScoresProps) {
  if (items.length === 0) return null;

  return (
    <section className={className} aria-label={heading}>
      <h3 className="mb-2.5 text-[11px] font-semibold uppercase tracking-widest text-zenodrift-text-muted">
        {heading}
      </h3>
      <ul className="space-y-1.5">
        {items.map((r, i) => {
          const reasoning = r.reasoning?.trim() || "No reasoning provided.";
          return (
            <li key={`${r.name}-${i}`}>
              <details className="group rounded-lg border border-slate-200/90 bg-white shadow-sm transition-colors open:bg-slate-50/80 open:ring-1 open:ring-slate-100">
                <summary
                  className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-sm font-medium text-zenodrift-text-strong marker:hidden [&::-webkit-details-marker]:hidden"
                  title={reasoning.length > 120 ? `${reasoning.slice(0, 117)}…` : reasoning}
                >
                  <span className="min-w-0 flex-1 leading-snug">
                    <span className="text-zenodrift-text">{r.name}</span>
                    <span className="text-zenodrift-text-muted">: </span>
                    <span className={`tabular-nums font-semibold ${scoreColorClass(r.score)}`}>
                      {formatScoreTen(r.score)}
                    </span>
                    <span className="text-zenodrift-text-muted">/10</span>
                  </span>
                  <svg
                    className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="border-t border-slate-100 px-3 pb-3 pt-2">
                  <p className="border-l-2 border-zenodrift-accent/40 pl-3 text-sm leading-relaxed text-zenodrift-text">
                    {reasoning}
                  </p>
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
