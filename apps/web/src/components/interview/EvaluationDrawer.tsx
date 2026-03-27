"use client";

import { useEffect, useCallback, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type {
  EvaluationCitation,
  EvidenceUsedItem,
  InterviewEvaluateResponse,
} from "@/lib/api";

interface EvaluationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  result: InterviewEvaluateResponse | null;
  onRetry?: () => void;
  onNextQuestion?: () => void;
  canNext?: boolean;
}

const scoreColorLlm = (llmScore: number) =>
  llmScore >= 8 ? "text-emerald-600" : llmScore >= 6 ? "text-amber-600" : "text-red-600";

const springTransition = {
  type: "spring" as const,
  stiffness: 400,
  damping: 30,
};

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(max-width: 640px)");
    setIsMobile(m.matches);
    const listener = () => setIsMobile(m.matches);
    m.addEventListener("change", listener);
    return () => m.removeEventListener("change", listener);
  }, []);
  return isMobile;
}

function CollapsibleSection({
  id,
  emoji,
  title,
  defaultOpen,
  children,
}: {
  id: string;
  emoji: string;
  title: string;
  defaultOpen: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = `${id}-panel`;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-sm">
      <button
        type="button"
        id={`${id}-trigger`}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left transition-colors hover:bg-slate-50/90 sm:px-4"
      >
        <span className="text-sm font-semibold leading-snug text-zenodrift-text-strong">
          <span className="mr-2 select-none" aria-hidden>
            {emoji}
          </span>
          {title}
        </span>
        <svg
          className={`h-5 w-5 shrink-0 text-slate-500 transition-transform duration-200 ${
            open ? "rotate-180" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div
          id={panelId}
          role="region"
          aria-labelledby={`${id}-trigger`}
          className="border-t border-slate-100"
        >
          <div className="max-h-[min(55vh,28rem)] overflow-y-auto px-3 py-3 sm:px-4 sm:py-4">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

function evidenceRows(result: InterviewEvaluateResponse): Array<{
  key: string;
  page: number;
  text: string;
  sourceLabel?: string;
}> {
  const citations = result.citations ?? [];
  if (citations.length > 0) {
    return citations.map((c: EvaluationCitation, i: number) => ({
      key: `c-${c.chunk_id}-${i}`,
      page: c.page_number ?? 0,
      text: c.text?.trim() || "—",
      sourceLabel: "Job description",
    }));
  }
  const used = result.evidence_used ?? [];
  return used.map((e: EvidenceUsedItem, i: number) => ({
    key: `e-${e.chunkId ?? e.sourceId}-${i}`,
    page: e.page ?? 0,
    text: e.quote?.trim() || "—",
    sourceLabel: e.sourceType === "jd" ? "Job description" : e.sourceTitle || e.sourceType || "Source",
  }));
}

export function EvaluationDrawer({
  isOpen,
  onClose,
  result,
  onRetry,
  onNextQuestion,
  canNext,
}: EvaluationDrawerProps) {
  const isMobile = useIsMobile();
  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "";
    };
  }, [isOpen, handleEscape]);

  const drawerVariants = {
    closed: isMobile ? { y: "100%" } : { x: "100%" },
    open: isMobile ? { y: 0 } : { x: 0 },
  };

  const rows = result ? evidenceRows(result) : [];

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />

          <motion.aside
            initial={drawerVariants.closed}
            animate={drawerVariants.open}
            exit={drawerVariants.closed}
            transition={springTransition}
            role="dialog"
            aria-label="Evaluation results"
            className="fixed bottom-0 right-0 z-50 flex h-[90vh] w-full max-w-lg flex-col bg-white shadow-2xl sm:top-0 sm:h-full sm:max-h-none sm:rounded-l-2xl"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3 sm:px-6">
              <h2 className="text-lg font-semibold text-zenodrift-text-strong">Evaluation</h2>
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-zenodrift-text-muted transition-colors hover:bg-slate-100 hover:text-zenodrift-text-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2"
                aria-label="Close drawer"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-5 sm:px-6">
              {result && (
                <div className="flex flex-col gap-4 pb-4">
                  {result.summary?.trim() ? (
                    <div className="rounded-xl border border-slate-200/90 bg-white px-4 py-3.5 shadow-sm sm:px-5">
                      <p className="text-[11px] font-semibold uppercase tracking-widest text-zenodrift-text-muted">
                        Summary
                      </p>
                      <p className="mt-2 text-sm leading-relaxed text-zenodrift-text">{result.summary.trim()}</p>
                    </div>
                  ) : null}

                  {/* Score — prominent */}
                  <div className="rounded-2xl border border-slate-200/90 bg-gradient-to-b from-slate-50 to-white px-5 py-6 text-center shadow-sm ring-1 ring-slate-100/80">
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-zenodrift-text-muted">
                      Score
                    </p>
                    <div className="mt-2 flex flex-wrap items-baseline justify-center gap-x-2 gap-y-1">
                      <span
                        className={`text-5xl font-bold tabular-nums tracking-tight ${scoreColorLlm(result.llm_score)}`}
                      >
                        {result.llm_score.toFixed(1)}
                      </span>
                      <span className="text-xl font-medium text-zenodrift-text-muted">/ 10</span>
                    </div>
                    <p className="mt-3 text-sm text-zenodrift-text-muted">
                      Rubric{" "}
                      <span className="font-semibold tabular-nums text-zenodrift-text">
                        {result.score.toFixed(0)}
                      </span>
                      <span className="text-zenodrift-text-muted"> / 100</span>
                    </p>
                    {result.score_reasoning?.trim() ? (
                      <div className="mt-4 w-full text-left">
                        <p className="text-[11px] font-semibold uppercase tracking-widest text-zenodrift-text-muted">
                          Why this score
                        </p>
                        <p className="mt-1.5 text-sm leading-relaxed text-zenodrift-text">
                          {result.score_reasoning.trim()}
                        </p>
                      </div>
                    ) : null}
                    <div className="mt-4 flex flex-wrap justify-center gap-2">
                      {onRetry && (
                        <button
                          type="button"
                          onClick={() => {
                            onRetry();
                            onClose();
                          }}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-zenodrift-text transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2"
                        >
                          Try again
                        </button>
                      )}
                      {onNextQuestion && canNext && (
                        <button
                          type="button"
                          onClick={() => {
                            onNextQuestion();
                            onClose();
                          }}
                          className="rounded-lg bg-zenodrift-accent px-4 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-zenodrift-accent-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2"
                        >
                          Next question
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Strengths */}
                  {result.strengths.length > 0 && (
                    <CollapsibleSection id="eval-strengths" emoji="✅" title="Strengths" defaultOpen>
                      <ul className="space-y-3 text-sm text-zenodrift-text">
                        {result.strengths.map((s, i) => (
                          <li key={i} className="list-none">
                            <div className="flex gap-2">
                              <span className="mt-0.5 shrink-0 text-emerald-600" aria-hidden>
                                •
                              </span>
                              <div className="min-w-0 flex-1 space-y-2">
                                <p className="leading-relaxed">{s.text}</p>
                                {s.highlight?.trim() ? (
                                  <p className="rounded-lg border border-emerald-200/90 bg-emerald-50/95 px-3 py-2 text-xs font-medium leading-relaxed text-emerald-950">
                                    <span className="text-emerald-700">Matched in your answer: </span>
                                    “{s.highlight}”
                                  </p>
                                ) : null}
                                {s.evidence?.trim() ? (
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-900/75">
                                      Evidence (quote)
                                    </p>
                                    <p className="mt-0.5 text-xs leading-relaxed text-zenodrift-text-muted">
                                      {s.evidence}
                                    </p>
                                  </div>
                                ) : null}
                                {s.impact?.trim() ? (
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-900/75">
                                      Why it matters for this role
                                    </p>
                                    <p className="mt-0.5 text-sm leading-relaxed text-zenodrift-text">{s.impact}</p>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </CollapsibleSection>
                  )}

                  {/* Gaps */}
                  {result.gaps.length > 0 && (
                    <CollapsibleSection id="eval-gaps" emoji="❌" title="Gaps" defaultOpen>
                      <ul className="space-y-4 text-sm">
                        {result.gaps.map((g, i) => {
                          const hasGapFields =
                            "missing" in g || "improvement" in g || "jd_alignment" in g;
                          const legacyShape = !hasGapFields;
                          return (
                            <li key={i} className="list-none rounded-lg bg-amber-50/60 px-3 py-2.5">
                              {legacyShape && g.text?.trim() ? (
                                <>
                                  <p className="font-medium text-amber-950">What’s missing</p>
                                  <p className="mt-1 leading-relaxed text-zenodrift-text">{g.text}</p>
                                </>
                              ) : null}
                              {!legacyShape && g.text?.trim() ? (
                                <>
                                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-900/80">
                                    What you said
                                  </p>
                                  <p className="mt-0.5 leading-relaxed text-zenodrift-text">{g.text}</p>
                                </>
                              ) : null}
                              {!legacyShape && g.missing?.trim() ? (
                                <>
                                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-900/80">
                                    What’s missing
                                  </p>
                                  <p className="mt-0.5 text-sm leading-relaxed text-amber-950">{g.missing}</p>
                                </>
                              ) : null}
                              {g.expected?.trim() ? (
                                <>
                                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-900/80">
                                    What the interviewer expected
                                  </p>
                                  <p className="mt-0.5 text-sm leading-relaxed text-amber-950/95">{g.expected}</p>
                                </>
                              ) : null}
                              {!legacyShape && g.jd_alignment?.trim() ? (
                                <>
                                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-900/80">
                                    JD alignment
                                  </p>
                                  <p className="mt-0.5 text-sm leading-relaxed text-amber-950">
                                    {g.jd_alignment}
                                  </p>
                                </>
                              ) : null}
                              {!legacyShape && g.improvement?.trim() ? (
                                <>
                                  <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-900/80">
                                    Try saying instead
                                  </p>
                                  <p className="mt-0.5 text-sm font-medium leading-relaxed text-amber-950">
                                    {g.improvement}
                                  </p>
                                </>
                              ) : null}
                            </li>
                          );
                        })}
                      </ul>
                    </CollapsibleSection>
                  )}

                  {/* Evidence (JD chunks) */}
                  <CollapsibleSection id="eval-evidence" emoji="📄" title="Evidence" defaultOpen={rows.length > 0}>
                    {rows.length === 0 ? (
                      <p className="text-sm text-zenodrift-text-muted">No cited job description excerpts for this evaluation.</p>
                    ) : (
                      <ul className="space-y-3">
                        {rows.map((row) => (
                          <li
                            key={row.key}
                            className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm"
                          >
                            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-zenodrift-text-muted">
                              <span className="font-mono font-medium text-zenodrift-accent">
                                Page {row.page}
                              </span>
                              {row.sourceLabel ? (
                                <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                                  {row.sourceLabel}
                                </span>
                              ) : null}
                            </div>
                            <p className="mt-1.5 leading-relaxed text-zenodrift-text">{row.text}</p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </CollapsibleSection>

                  {result.improved_answer?.trim() ? (
                    <div className="rounded-xl border border-slate-100 bg-slate-50/50 px-3 py-3 sm:px-4">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-zenodrift-text-muted">
                        Stronger answer (9–10 / 10)
                      </h3>
                      <p className="mt-1 text-[11px] leading-snug text-zenodrift-text-muted">
                        Rewritten from your answer—same idea, more depth, realistic detail.
                      </p>
                      <p className="mt-2 text-sm leading-relaxed text-zenodrift-text">{result.improved_answer}</p>
                    </div>
                  ) : null}

                  {result.follow_up_questions.length > 0 ? (
                    <div className="rounded-xl border border-slate-100 px-3 py-3 sm:px-4">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-zenodrift-text-muted">
                        Follow-up questions
                      </h3>
                      <ul className="mt-2 space-y-1.5 text-sm text-zenodrift-text">
                        {result.follow_up_questions.map((q, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="text-zenodrift-text-muted">•</span>
                            <span>{q}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
