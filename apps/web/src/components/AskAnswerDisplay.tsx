"use client";

import type { AskStructuredAnswer } from "@/lib/api";

function scoreTone(score: number): string {
  if (score >= 75) return "bg-emerald-100 text-emerald-900 ring-emerald-200/80";
  if (score >= 50) return "bg-amber-100 text-amber-950 ring-amber-200/80";
  if (score >= 25) return "bg-orange-100 text-orange-950 ring-orange-200/70";
  return "bg-slate-100 text-slate-800 ring-slate-200/80";
}

export function AskAnswerDisplay({ data }: { data: AskStructuredAnswer }) {
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

      {data.key_job_requirements.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
            Key job requirements
          </h3>
          <ul className="list-inside list-disc space-y-1.5 text-sm leading-relaxed text-zenodrift-text">
            {data.key_job_requirements.map((req, i) => (
              <li key={i}>{req}</li>
            ))}
          </ul>
        </section>
      )}

      {data.matches.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-emerald-800">
            Strong matches
          </h3>
          <ul className="space-y-4">
            {data.matches.map((m, i) => (
              <li
                key={i}
                className="rounded-xl border border-emerald-200/60 bg-emerald-50/40 px-4 py-3 text-sm shadow-sm"
              >
                <p className="font-medium text-zenodrift-text-strong">
                  {m.requirement}
                </p>
                <p className="mt-2 text-zenodrift-text">
                  <span className="font-medium text-zenodrift-text-strong">
                    From your resume:{" "}
                  </span>
                  {m.candidate_experience}
                </p>
                {m.alignment_notes?.trim() ? (
                  <p className="mt-2 text-xs leading-relaxed text-zenodrift-text-muted">
                    {m.alignment_notes}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.gaps.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-amber-900">
            Gaps
          </h3>
          <ul className="space-y-3">
            {data.gaps.map((g, i) => (
              <li
                key={i}
                className="rounded-xl border border-amber-200/70 bg-amber-50/50 px-4 py-3 text-sm"
              >
                <p className="font-medium text-zenodrift-text-strong">
                  {g.requirement}
                </p>
                <p className="mt-1.5 text-zenodrift-text">{g.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.reasoning.trim() ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
            Summary
          </h3>
          <p className="text-sm leading-relaxed text-zenodrift-text">
            {data.reasoning}
          </p>
        </section>
      ) : null}
    </div>
  );
}
