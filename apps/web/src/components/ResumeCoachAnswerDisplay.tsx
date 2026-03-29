"use client";

import type { ResumeCoachStructuredAnswer } from "@/lib/api";

export function ResumeCoachAnswerDisplay({ data }: { data: ResumeCoachStructuredAnswer }) {
  return (
    <div className="space-y-8 text-zenodrift-text">
      {data.coaching_reply.trim() ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
            Here&apos;s the gist
          </h3>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.coaching_reply}</p>
        </section>
      ) : null}

      {data.prioritized_edits.length > 0 ? (
        <section>
          <h3 className="mb-3 text-sm font-semibold text-zenodrift-text-strong">
            Ideas to try
          </h3>
          <ul className="space-y-4">
            {data.prioritized_edits.map((e, i) => (
              <li
                key={i}
                className="rounded-xl border border-orange-200/60 bg-orange-50/40 px-4 py-3 text-sm shadow-sm"
              >
                <p className="font-medium text-zenodrift-text-strong">{e.focus}</p>
                <p className="mt-2 text-zenodrift-text">
                  <span className="font-medium text-zenodrift-text-strong">What we see: </span>
                  {e.observation}
                </p>
                <p className="mt-2 text-zenodrift-text">
                  <span className="font-medium text-zenodrift-text-strong">Try: </span>
                  {e.suggestion}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.strengths_to_keep.length > 0 ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-emerald-900">
            What&apos;s already working
          </h3>
          <ul className="list-inside list-disc space-y-1.5 text-sm leading-relaxed">
            {data.strengths_to_keep.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {data.reasoning.trim() ? (
        <section>
          <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
            Where this ties back to your resume
          </h3>
          <p className="text-sm leading-relaxed text-zenodrift-text-muted">{data.reasoning}</p>
        </section>
      ) : null}
    </div>
  );
}
