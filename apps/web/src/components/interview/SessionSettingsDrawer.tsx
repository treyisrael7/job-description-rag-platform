"use client";

import { useEffect, useCallback, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface SessionSettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  mode: string;
  difficulty: string;
  questionCount: number;
  currentIndex: number;
  onPrev: () => void;
  onNext: () => void;
  canPrev: boolean;
  canNext: boolean;
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

export function SessionSettingsDrawer({
  isOpen,
  onClose,
  mode,
  difficulty,
  questionCount,
  currentIndex,
  onPrev,
  onNext,
  canPrev,
  canNext,
}: SessionSettingsDrawerProps) {
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
    closed: isMobile ? { y: "100%" } : { x: "-100%" },
    open: isMobile ? { y: 0 } : { x: 0 },
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[100] bg-slate-900/30 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <motion.aside
            initial={drawerVariants.closed}
            animate={drawerVariants.open}
            exit={drawerVariants.closed}
            transition={springTransition}
            role="dialog"
            aria-label="Session settings"
            className="fixed bottom-0 left-0 z-[101] flex h-[50vh] w-full flex-col border-r border-slate-200 bg-white shadow-2xl sm:top-0 sm:h-full sm:max-h-none sm:w-[280px] sm:rounded-r-2xl"
          >
            <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3">
              <h2 className="text-sm font-semibold text-zenodrift-text-strong">Session Settings</h2>
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-zenodrift-text-muted transition-colors hover:bg-slate-100"
                aria-label="Close"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
              <div>
                <p className="mb-1 text-xs font-medium text-zenodrift-text-muted">Profile</p>
                <p className="text-sm text-zenodrift-text-strong">
                  {mode === "role_driven"
                    ? "Role-driven"
                    : mode === "technical"
                      ? "Role-specific"
                      : mode === "behavioral"
                        ? "Behavioral"
                        : mode === "mixed"
                          ? "Mixed"
                          : mode}
                </p>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-zenodrift-text-muted">Difficulty</p>
                <p className="text-sm text-zenodrift-text-strong">{difficulty}</p>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-zenodrift-text-muted">Questions</p>
                <p className="text-sm text-zenodrift-text-strong">{questionCount}</p>
              </div>
              <div className="border-t border-slate-100 pt-4">
                <p className="mb-2 text-xs font-medium text-zenodrift-text-muted">Navigate</p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onPrev}
                    disabled={!canPrev}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-zenodrift-text disabled:opacity-40"
                  >
                    ← Prev
                  </button>
                  <span className="text-sm text-zenodrift-text-muted">
                    {currentIndex + 1} / {questionCount}
                  </span>
                  <button
                    onClick={onNext}
                    disabled={!canNext}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-zenodrift-text disabled:opacity-40"
                  >
                    Next →
                  </button>
                </div>
              </div>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
