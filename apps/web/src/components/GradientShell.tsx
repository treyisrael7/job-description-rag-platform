"use client";

import { type ReactNode } from "react";

export interface GradientShellProps {
  children: ReactNode;
  /** Optional header slot (legacy, prefer hero for title) */
  header?: ReactNode;
  /** Optional hero - title/subtitle, shown above content */
  hero?: ReactNode;
  /** Override max-width of the content area (default 1200px) */
  maxWidth?: string;
  /** Extra class names for the content wrapper */
  className?: string;
  /** When true, content fits viewport with no extra padding/gap (for Interview) */
  fillViewport?: boolean;
}

export function GradientShell({
  children,
  header,
  hero,
  maxWidth = "1200px",
  className = "",
  fillViewport = false,
}: GradientShellProps) {
  return (
    <main
      className={`relative ${fillViewport ? "min-h-screen" : "min-h-[100dvh]"}`}
      role="main"
      aria-label="Main content"
    >
      {/* Zenodrift multi-layer atmospheric background */}
      <div className="zenodrift-bg" aria-hidden="true">
        <div className="zenodrift-bg-layer zenodrift-bg-base" />
        <div className="zenodrift-bg-layer zenodrift-bg-bloom-1" />
        <div className="zenodrift-bg-layer zenodrift-bg-bloom-2" />
        <div className="zenodrift-bg-layer zenodrift-bg-vignette" />
        <div className="zenodrift-bg-layer zenodrift-bg-grid" />
      </div>
      <div
        className={`relative z-10 mx-auto flex flex-col ${
          fillViewport
            ? "h-[100dvh] max-h-[100dvh] min-h-0 overflow-hidden gap-0 pt-14 pb-4 px-4 sm:px-6"
            : `min-h-[100dvh] gap-6 px-6 py-8 sm:px-8 sm:py-10 lg:px-10`
        } ${className}`}
        style={fillViewport ? { maxWidth: "980px" } : { maxWidth }}
      >
        {header && (
          <header className="border-b border-white/30 px-4 py-4 sm:px-6">
            {header}
          </header>
        )}
        {hero && <div className="text-center">{hero}</div>}
        {children}
      </div>
    </main>
  );
}
