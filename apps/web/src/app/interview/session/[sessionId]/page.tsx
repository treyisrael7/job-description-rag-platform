"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { GradientShell } from "@/components/GradientShell";
import { InterviewSessionView } from "@/components/interview/InterviewSessionView";
import { getInterviewSession, getDocument, ApiError } from "@/lib/api";

export default function InterviewSessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<Awaited<ReturnType<typeof getInterviewSession>> | null>(null);
  const [documentFilename, setDocumentFilename] = useState<string>("Job Description");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSession = useCallback(async () => {
    try {
      setError(null);
      const s = await getInterviewSession(sessionId);
      setSession(s);
      try {
        const doc = await getDocument(s.document_id);
        setDocumentFilename(doc.filename);
      } catch {
        // ignore, use default
      }
      return s;
    } catch (e) {
      setError(
        e instanceof ApiError
          ? String(e.detail || e.message)
          : "Failed to load session"
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  return (
    <GradientShell fillViewport>
      {loading && (
        <div className="flex flex-1 items-center justify-center py-8">
          <div
            className="h-10 w-10 animate-spin rounded-full border-2 border-white/60 border-t-zenodrift-accent"
            aria-label="Loading session"
          />
        </div>
      )}

      {error && !session && (
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

      {session && !loading && (
        <InterviewSessionView
            documentId={session.document_id}
            documentFilename={documentFilename}
            session={{
              sessionId: session.id,
              questions: session.questions,
              mode: session.mode.charAt(0).toUpperCase() + session.mode.slice(1),
              difficulty: session.difficulty.charAt(0).toUpperCase() + session.difficulty.slice(1),
            }}
            onNewSessionHref={`/interview/setup/${session.document_id}`}
            backHref="/dashboard"
          />
      )}
    </GradientShell>
  );
}
