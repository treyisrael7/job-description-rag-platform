"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { GradientShell } from "@/components/GradientShell";
import { InterviewSetupPanel } from "@/components/interview/InterviewSetupPanel";
import {
  getDocument,
  ApiError,
  type DocumentSummary,
} from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

export default function InterviewSetupPage() {
  const params = useParams();
  const id = params.id as string;
  const [doc, setDoc] = useState<DocumentSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDoc = useCallback(async () => {
    try {
      setError(null);
      const d = await getDocument(id);
      setDoc(d);
      return d;
    } catch (e) {
      setError(
        e instanceof ApiError
          ? String(e.detail || e.message)
          : "Failed to load document"
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchDoc();
  }, [fetchDoc]);

  useEffect(() => {
    if (!doc || doc.status !== "processing") return;
    pollRef.current = setInterval(fetchDoc, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- doc omitted to avoid polling loop
  }, [doc?.status, fetchDoc]);

  useEffect(() => {
    if (doc?.status !== "processing" && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [doc?.status]);

  const showSetup =
    doc?.status === "ready" && doc?.doc_domain === "job_description";

  return (
    <GradientShell
      hero={
        showSetup ? (
          <header className="text-center">
            <h1 className="relative inline-block pb-2 text-2xl font-semibold tracking-tight text-zenodrift-text-strong sm:text-3xl">
              Interview Setup
              <span
                className="absolute bottom-0 left-1/2 h-0.5 w-10 -translate-x-1/2 rounded-full bg-zenodrift-accent"
                aria-hidden
              />
            </h1>
            <p className="mt-3 text-base font-normal leading-relaxed text-zenodrift-text-muted">
              Configure your practice session for{" "}
              <span className="font-medium text-zenodrift-text">
                {doc?.filename?.replace(/\.pdf$/i, "") ?? ""}
              </span>
            </p>
          </header>
        ) : undefined
      }
    >
      {loading && (
        <div className="flex min-h-[400px] items-center justify-center">
          <div
            className="h-10 w-10 animate-spin rounded-full border-2 border-white/60 border-t-zenodrift-accent"
            aria-label="Loading document"
          />
        </div>
      )}

      {error && !doc && (
        <div
          className="dashboard-card w-full max-w-md border-red-200/50 bg-red-50/60 p-5 text-red-700"
          role="alert"
        >
          {error}
          <Link
            href="/dashboard"
            className="mt-4 block text-sm font-medium text-zenodrift-accent hover:text-zenodrift-accent-hover focus:outline-none focus-visible:underline"
          >
            ← Back to dashboard
          </Link>
        </div>
      )}

      {doc && !loading && (
        <div className="flex flex-col items-center gap-8">
          {doc.status === "processing" && (
            <div className="dashboard-card w-full max-w-md px-6 py-8 text-center">
              <div
                className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-amber-300 border-t-zenodrift-accent"
                aria-hidden
              />
              <p className="text-amber-800 font-medium">
                Document is being processed…
              </p>
              <p className="mt-2 text-sm text-amber-700">
                This page will update automatically when ready.
              </p>
            </div>
          )}

          {(doc.status === "uploaded" || doc.status === "pending") && (
            <div className="dashboard-card w-full max-w-md px-6 py-8 text-center">
              <p className="text-amber-800">
                Document has not been processed yet.
              </p>
              <Link
                href="/dashboard"
                className="mt-4 inline-block text-sm font-medium text-zenodrift-accent hover:text-zenodrift-accent-hover focus:outline-none focus-visible:underline"
              >
                Go to dashboard to process
              </Link>
            </div>
          )}

          {doc.status === "failed" && (
            <div className="dashboard-card w-full max-w-md border-red-200/50 bg-red-50/60 px-6 py-8 text-center">
              <p className="text-red-700">
                {doc.error_message || "Document processing failed."}
              </p>
              <Link
                href="/dashboard"
                className="mt-4 inline-block text-sm font-medium text-zenodrift-accent hover:text-zenodrift-accent-hover focus:outline-none focus-visible:underline"
              >
                ← Back to dashboard
              </Link>
            </div>
          )}

          {showSetup && doc && (
            <div className="w-full max-w-lg space-y-6">
              <InterviewSetupPanel
                documentId={id}
                roleProfile={doc.role_profile ?? undefined}
                competencies={doc.competencies}
                coveragePracticed={doc.coverage_practiced ?? 0}
                coverageTotal={doc.coverage_total ?? 0}
              />
              <div className="text-center">
                <Link
                  href="/dashboard"
                  className="text-sm text-zenodrift-text-muted hover:text-zenodrift-text"
                >
                  ← Back to dashboard
                </Link>
              </div>
            </div>
          )}

          {doc.status === "ready" && doc?.doc_domain !== "job_description" && (
            <div className="dashboard-card w-full max-w-md px-6 py-8 text-center">
              <p className="text-zenodrift-text-muted">
                This document type does not support interview prep.
              </p>
              <Link
                href={`/documents/${id}`}
                className="mt-4 inline-block text-sm font-medium text-zenodrift-accent hover:text-zenodrift-accent-hover focus:outline-none focus-visible:underline"
              >
                Open document
              </Link>
            </div>
          )}
        </div>
      )}
    </GradientShell>
  );
}
