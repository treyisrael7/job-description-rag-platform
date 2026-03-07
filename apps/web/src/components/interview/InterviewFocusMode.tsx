"use client";

import Link from "next/link";

interface InterviewFocusModeProps {
  documentId: string;
  documentFilename: string;
}

/**
 * Interview Prep tab on document page. Routes to dedicated Interview Setup screen.
 */
export function InterviewFocusMode({
  documentId,
  documentFilename,
}: InterviewFocusModeProps) {
  return (
    <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl bg-white/50 py-14 shadow-zenodrift-soft backdrop-blur-sm">
      <p className="mb-6 text-center text-zenodrift-text-muted">
        Practice interview questions with AI-powered, evidence-backed feedback
        for <span className="font-medium text-zenodrift-text">{documentFilename.replace(/\.pdf$/i, "")}</span>.
      </p>
      <Link
        href={`/interview/setup/${documentId}`}
        className="rounded-xl bg-zenodrift-accent px-6 py-3 text-sm font-medium text-white shadow-zenodrift-soft transition-all duration-200 hover:bg-zenodrift-accent-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-zenodrift-accent focus-visible:ring-offset-2"
      >
        Start Interview
      </Link>
    </div>
  );
}
