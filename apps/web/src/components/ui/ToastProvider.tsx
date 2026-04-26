"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

type ToastTone = "success" | "error" | "info";

type ToastInput = {
  message: string;
  tone?: ToastTone;
  durationMs?: number;
};

type ToastRecord = {
  id: string;
  message: string;
  tone: ToastTone;
  durationMs: number;
};

type ToastContextValue = {
  showToast: (toast: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_STYLE: Record<ToastTone, string> = {
  success: "border-emerald-200/70 bg-emerald-50/95 text-emerald-900",
  error: "border-red-200/70 bg-red-50/95 text-red-900",
  info: "border-slate-200/80 bg-white/95 text-zenodrift-text-strong",
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);
  const reduceMotion = useReducedMotion();

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    ({ message, tone = "info", durationMs = 2800 }: ToastInput) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setToasts((prev) => [...prev, { id, message, tone, durationMs }]);
      window.setTimeout(() => removeToast(id), durationMs);
    },
    [removeToast]
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(92vw,360px)] flex-col gap-2"
        aria-live="polite"
        aria-atomic="true"
      >
        <AnimatePresence initial={false}>
          {toasts.map((toast) => (
            <motion.div
              key={toast.id}
              className={`pointer-events-auto rounded-xl border px-4 py-3 text-sm shadow-lg backdrop-blur-sm ${TOAST_STYLE[toast.tone]}`}
              {...(reduceMotion
                ? { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
                : {
                    initial: { opacity: 0, x: 18, y: 8 },
                    animate: { opacity: 1, x: 0, y: 0 },
                    exit: { opacity: 0, x: 10, y: 2 },
                    transition: { duration: 0.22, ease: [0.22, 1, 0.36, 1] },
                  })}
            >
              <div className="flex items-start justify-between gap-3">
                <p className="leading-relaxed">{toast.message}</p>
                <button
                  type="button"
                  onClick={() => removeToast(toast.id)}
                  className="rounded-md px-1.5 py-0.5 text-xs text-current/70 transition hover:text-current focus:outline-none focus-visible:ring-2 focus-visible:ring-current/30"
                  aria-label="Dismiss notification"
                >
                  Dismiss
                </button>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
