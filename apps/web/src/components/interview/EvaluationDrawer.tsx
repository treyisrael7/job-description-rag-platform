"use client";

import { useEffect, useCallback, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { InterviewEvaluateResponse } from "@/lib/api";

interface EvaluationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  result: InterviewEvaluateResponse | null;
  onRetry?: () => void;
  onNextQuestion?: () => void;
  canNext?: boolean;
}

const scoreColor = (score: number) =>
  score >= 8 ? "text-emerald-600" : score >= 6 ? "text-amber-600" : "text-red-600";

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

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-slate-900/30 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />

          {/* Drawer: right on desktop, bottom sheet on mobile */}
          <motion.aside
            initial={drawerVariants.closed}
            animate={drawerVariants.open}
            exit={drawerVariants.closed}
            transition={springTransition}
            role="dialog"
            aria-label="Evaluation results"
            className="fixed bottom-0 right-0 z-50 flex h-[85vh] w-full max-w-md flex-col bg-white shadow-2xl sm:top-0 sm:h-full sm:max-h-none sm:w-[400px] sm:rounded-l-2xl"
          >
        {/* Drawer header */}
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

        {/* Drawer content */}
        <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          {result && (
            <div className="space-y-6">
              {/* Score */}
              <div className="flex items-center justify-between">
                <span className={`text-3xl font-bold ${scoreColor(result.score)}`}>
                  {result.score.toFixed(1)}/10
                </span>
                <div className="flex gap-2">
                  {onRetry && (
                    <button
                      onClick={() => {
                        onRetry();
                        onClose();
                      }}
                      className="text-sm font-medium text-orange-600 transition-colors hover:text-orange-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2 focus-visible:rounded"
                    >
                      Try again
                    </button>
                  )}
                  {onNextQuestion && canNext && (
                    <button
                      onClick={() => {
                        onNextQuestion();
                        onClose();
                      }}
                      className="text-sm font-medium text-orange-600 transition-colors hover:text-orange-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400 focus-visible:ring-offset-2 focus-visible:rounded"
                    >
                      Next question
                    </button>
                  )}
                </div>
              </div>

              {result.strengths.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">Strengths</h3>
                  <ul className="space-y-1.5 text-sm text-zenodrift-text">
                    {result.strengths.map((s, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-emerald-500">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.gaps.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">Gaps</h3>
                  <ul className="space-y-1.5 text-sm text-zenodrift-text">
                    {result.gaps.map((g, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-amber-500">•</span>
                        <span>{g}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.improved_answer && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">Improved Answer</h3>
                  <p className="text-sm leading-relaxed text-zenodrift-text">
                    {result.improved_answer}
                  </p>
                </div>
              )}

              {result.follow_up_questions.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-zenodrift-text-strong">
                    Follow-up Questions
                  </h3>
                  <ul className="space-y-1.5 text-sm text-zenodrift-text">
                    {result.follow_up_questions.map((q, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-zenodrift-text-muted">•</span>
                        <span>{q}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <p className="text-xs text-zenodrift-text-muted">
                Open <strong>Reference</strong> → Evidence for cited excerpts.
              </p>
            </div>
          )}
        </div>
      </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
