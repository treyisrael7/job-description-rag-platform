"use client";

import { useEffect, useCallback, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type {
  InterviewQuestion,
  InterviewEvaluateResponse,
  EvidenceUsedItem,
} from "@/lib/api";

type Tab = "evidence" | "rubric";

interface ReferenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  question: InterviewQuestion | null;
  lastEval: InterviewEvaluateResponse | null;
  initialTab?: Tab;
}

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

function buildEvidenceMap(evidence: EvidenceUsedItem[]): Map<string, EvidenceUsedItem> {
  const m = new Map<string, EvidenceUsedItem>();
  for (const e of evidence) {
    const k = e.chunkId ?? e.sourceId;
    if (k) m.set(k, e);
  }
  return m;
}

export function ReferenceDrawer({
  isOpen,
  onClose,
  question,
  lastEval,
  initialTab = "evidence",
}: ReferenceDrawerProps) {
  const isMobile = useIsMobile();
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  const highlightedIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (isOpen) setActiveTab(initialTab);
  }, [isOpen, initialTab]);

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

  const handleScrollToEvidence = (id: string) => {
    highlightedIdRef.current = id;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      el.classList.add("ring-2", "ring-zenodrift-accent", "ring-offset-2");
      setTimeout(() => {
        el.classList.remove("ring-2", "ring-zenodrift-accent", "ring-offset-2");
        highlightedIdRef.current = null;
      }, 1500);
    }
  };

  const evidenceMap = lastEval?.evidence_used?.length
    ? buildEvidenceMap(lastEval.evidence_used)
    : new Map<string, EvidenceUsedItem>();

  const strengthsCited = lastEval?.strengths_cited ?? [];
  const gapsCited = lastEval?.gaps_cited ?? [];

  const hasCitedEvidence = strengthsCited.length > 0 || gapsCited.length > 0;
  const hasFlatEvidence =
    !hasCitedEvidence &&
    (lastEval?.evidence_used?.length ?? 0) > 0;

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
            aria-label="Reference"
            className="fixed bottom-0 right-0 z-50 flex h-[85vh] w-full max-w-md flex-col bg-white shadow-2xl sm:top-0 sm:h-full sm:max-h-none sm:w-[420px] sm:rounded-l-2xl"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3 sm:px-6">
              <h2 className="text-lg font-semibold text-zenodrift-text-strong">
                Reference
              </h2>
              <div className="flex items-center gap-2">
                <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5">
                  <button
                    onClick={() => setActiveTab("evidence")}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      activeTab === "evidence"
                        ? "bg-white text-zenodrift-text-strong shadow-sm"
                        : "text-zenodrift-text-muted hover:text-zenodrift-text"
                    }`}
                  >
                    Evidence
                  </button>
                  <button
                    onClick={() => setActiveTab("rubric")}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                      activeTab === "rubric"
                        ? "bg-white text-zenodrift-text-strong shadow-sm"
                        : "text-zenodrift-text-muted hover:text-zenodrift-text"
                    }`}
                  >
                    Rubric
                  </button>
                </div>
                <button
                  onClick={onClose}
                  className="rounded-lg p-2 text-zenodrift-text-muted transition-colors hover:bg-slate-100 hover:text-zenodrift-text-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2"
                  aria-label="Close drawer"
                >
                  <svg
                    className="h-5 w-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
              {activeTab === "evidence" && (
                <div className="space-y-6">
                  {hasCitedEvidence && (
                    <>
                      {strengthsCited.length > 0 && (
                        <section>
                          <h3 className="mb-2 text-sm font-semibold text-emerald-700">
                            Strengths
                          </h3>
                          <ul className="space-y-2">
                            {strengthsCited.map((item, i) => (
                              <li key={i} className="space-y-1.5">
                                <p
                                  className="cursor-pointer text-sm text-zenodrift-text hover:text-zenodrift-accent hover:underline"
                                  onClick={() =>
                                    item.citations?.[0]?.chunkId &&
                                    handleScrollToEvidence(
                                      `evidence-strength-${i}-0`
                                    )
                                  }
                                  role="button"
                                >
                                  • {item.text}
                                </p>
                                {item.citations?.map((c, j) => {
                                  const ev = evidenceMap.get(c.chunkId);
                                  const id = `evidence-strength-${i}-${j}`;
                                  return ev ? (
                                    <div
                                      key={j}
                                      id={id}
                                      className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm transition-shadow"
                                    >
                                      <p className="text-zenodrift-text leading-relaxed">
                                        {ev.quote}
                                      </p>
                                      {ev.page != null && (
                                        <span className="mt-1 block text-xs text-zenodrift-text-muted">
                                          Page {ev.page}
                                        </span>
                                      )}
                                    </div>
                                  ) : null;
                                })}
                              </li>
                            ))}
                          </ul>
                        </section>
                      )}
                      {gapsCited.length > 0 && (
                        <section>
                          <h3 className="mb-2 text-sm font-semibold text-amber-700">
                            Gaps
                          </h3>
                          <ul className="space-y-2">
                            {gapsCited.map((item, i) => (
                              <li key={i} className="space-y-1.5">
                                <p
                                  className="cursor-pointer text-sm text-zenodrift-text hover:text-zenodrift-accent hover:underline"
                                  onClick={() =>
                                    item.citations?.[0]?.chunkId &&
                                    handleScrollToEvidence(
                                      `evidence-gap-${i}-0`
                                    )
                                  }
                                  role="button"
                                >
                                  • {item.text}
                                </p>
                                {item.citations?.map((c, j) => {
                                  const ev = evidenceMap.get(c.chunkId);
                                  const id = `evidence-gap-${i}-${j}`;
                                  return ev ? (
                                    <div
                                      key={j}
                                      id={id}
                                      className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm transition-shadow"
                                    >
                                      <p className="text-zenodrift-text leading-relaxed">
                                        {ev.quote}
                                      </p>
                                      {ev.page != null && (
                                        <span className="mt-1 block text-xs text-zenodrift-text-muted">
                                          Page {ev.page}
                                        </span>
                                      )}
                                    </div>
                                  ) : null;
                                })}
                              </li>
                            ))}
                          </ul>
                        </section>
                      )}
                    </>
                  )}
                  {hasFlatEvidence && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
                        Evidence used
                      </h3>
                      <ul className="space-y-3">
                        {lastEval!.evidence_used!.map((e, i) => (
                          <li
                            key={i}
                            className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm"
                          >
                            <p className="text-zenodrift-text leading-relaxed">
                              {e.quote}
                            </p>
                            {e.page != null && (
                              <span className="mt-1 block text-xs text-zenodrift-text-muted">
                                Page {e.page}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {lastEval?.citations && lastEval.citations.length > 0 && (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
                        Cited sources
                      </h3>
                      <ul className="space-y-3">
                        {lastEval.citations.map((c, i) => (
                          <li
                            key={`${c.chunk_id}-${i}`}
                            className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5 text-sm"
                          >
                            <span className="font-mono text-xs text-zenodrift-accent">
                              Page {c.page_number}
                            </span>
                            <p className="mt-1 text-zenodrift-text leading-relaxed">{c.text}</p>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}

                  {!hasCitedEvidence && !hasFlatEvidence && !lastEval?.citations?.length && (
                    <p className="text-sm text-zenodrift-text-muted">
                      Submit an answer to see evidence cited in the evaluation.
                    </p>
                  )}
                </div>
              )}

              {activeTab === "rubric" && (
                <div className="space-y-6">
                  {question?.competency_label?.trim() && (
                    <section>
                      <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wider text-zenodrift-text-muted">
                        Competency
                      </h3>
                      <p className="text-sm font-medium text-zenodrift-text-strong">
                        {question.competency_label}
                      </p>
                    </section>
                  )}
                  {question?.rubric_bullets?.length ? (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
                        What good looks like
                      </h3>
                      <ul className="list-inside list-disc space-y-2 text-sm text-zenodrift-text">
                        {question.rubric_bullets.map((b, i) => (
                          <li key={i}>{b}</li>
                        ))}
                      </ul>
                    </section>
                  ) : (
                    <p className="text-sm text-zenodrift-text-muted">
                      No rubric for this question.
                    </p>
                  )}
                  {question?.evidence?.length ? (
                    <section>
                      <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
                        What the JD emphasizes
                      </h3>
                      <ul className="space-y-3 text-sm text-zenodrift-text">
                        {question.evidence.map((e, i) => (
                          <li
                            key={i}
                            className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5"
                          >
                            <span className="font-mono text-xs text-zenodrift-accent">
                              Page {e.page_number}
                            </span>{" "}
                            {e.snippet}
                          </li>
                        ))}
                      </ul>
                    </section>
                  ) : (
                    question && (
                      <p className="text-sm text-zenodrift-text-muted">
                        No JD evidence for this question.
                      </p>
                    )
                  )}
                  {!question && (
                    <p className="text-sm text-zenodrift-text-muted">
                      No question selected.
                    </p>
                  )}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
