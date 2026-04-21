"use client";

import type { AnalyzeFitResult } from "@/lib/api";

function scoreTone(score: number): string {
  if (score >= 75) return "bg-emerald-100 text-emerald-900 ring-emerald-200/80";
  if (score >= 50) return "bg-amber-100 text-amber-950 ring-amber-200/80";
  if (score >= 25) return "bg-orange-100 text-orange-950 ring-orange-200/70";
  return "bg-slate-100 text-slate-800 ring-slate-200/80";
}

function importancePill(importance: string): string {
  const i = importance.toLowerCase();
  if (i === "high")
    return "bg-red-100 text-red-900 ring-red-200/70";
  if (i === "low")
    return "bg-slate-100 text-slate-700 ring-slate-200/70";
  return "bg-amber-50 text-amber-900 ring-amber-200/60";
}

export function AnalyzeFitDisplay({ data }: { data: AnalyzeFitResult }) {
  return (
    <div className="space-y-8 text-zenodrift-text">
      <div className="flex flex-wrap items-center gap-4">
        <div
          className={`rounded-2xl px-5 py-3 ring-1 ${scoreTone(data.fit_score)}`}
          aria-label={`Fit score ${data.fit_score} out of 100`}
        >
          <p className="text-xs font-semibold uppercase tracking-wide opacity-80">
            Fit score
          </p>
          <p className="text-3xl font-bold tabular-nums">{data.fit_score}</p>
          <p className="text-xs opacity-75">out of 100</p>
        </div>
      </div>

      {data.summary.trim() ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
            Summary
          </h3>
          <p className="text-sm leading-relaxed text-zenodrift-text">
            {data.summary}
          </p>
        </section>
      ) : null}

      {data.matches.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-emerald-800">
            Matches
          </h3>
          <ul className="space-y-4">
            {data.matches.map((m, i) => (
              <li
                key={i}
                className="rounded-xl border border-emerald-200/60 bg-emerald-50/40 px-4 py-3 text-sm shadow-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-zenodrift-text-strong">
                    {m.requirement}
                  </p>
                  {m.importance ? (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${importancePill(m.importance)}`}
                    >
                      {m.importance}
                    </span>
                  ) : null}
                  <span className="text-xs text-zenodrift-text-muted">
                    Confidence{" "}
                    {(m.confidence <= 1
                      ? m.confidence * 100
                      : m.confidence
                    ).toFixed(0)}
                    %
                  </span>
                </div>
                <p className="mt-2 text-zenodrift-text">
                  <span className="font-medium text-zenodrift-text-strong">
                    Resume evidence:{" "}
                  </span>
                  {m.resume_evidence}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.gaps.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-amber-900">Gaps</h3>
          <ul className="space-y-3">
            {data.gaps.map((g, i) => (
              <li
                key={i}
                className="rounded-xl border border-amber-200/70 bg-amber-50/50 px-4 py-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-zenodrift-text-strong">
                    {g.requirement}
                  </p>
                  {g.importance ? (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${importancePill(g.importance)}`}
                    >
                      {g.importance}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1.5 text-zenodrift-text">{g.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.recommendations.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-zenodrift-text-strong">
            Recommendations
          </h3>
          <ul className="space-y-4">
            {data.recommendations.map((r, i) => (
              <li
                key={i}
                className="rounded-xl border border-slate-200/80 bg-white/60 px-4 py-3 text-sm shadow-sm"
              >
                <p className="font-medium text-zenodrift-text-strong">{r.gap}</p>
                <p className="mt-2 text-zenodrift-text">{r.suggestion}</p>
                {r.missing_keywords?.length ? (
                  <div className="mt-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-zenodrift-text-muted">
                      Missing keywords
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {r.missing_keywords.map((kw, kwIndex) => (
                        <span
                          key={`${kw}-${kwIndex}`}
                          className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-900 ring-1 ring-amber-200/70"
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                {r.bullet_rewrite?.trim() ? (
                  <div className="mt-2 rounded-lg bg-emerald-50/70 px-3 py-2 text-xs text-emerald-950 ring-1 ring-emerald-200/70">
                    <p className="font-semibold uppercase tracking-wide text-emerald-800/90">
                      Bullet rewrite
                    </p>
                    <p className="mt-1">{r.bullet_rewrite}</p>
                  </div>
                ) : null}
                {r.example_resume_line?.trim() ? (
                  <p className="mt-2 rounded-lg bg-slate-50/90 px-3 py-2 text-xs italic text-zenodrift-text-muted">
                    Example line: {r.example_resume_line}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
