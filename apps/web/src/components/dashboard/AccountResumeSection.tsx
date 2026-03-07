"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getUserResume,
  presignUserResume,
  uploadToPresignedUrl,
  confirmUserResume,
  deleteUserResume,
  ApiError,
} from "@/lib/api";

interface AccountResumeSectionProps {
  onResumeChange?: () => void;
}

export function AccountResumeSection({ onResumeChange }: AccountResumeSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const [hasResume, setHasResume] = useState(false);
  const [filename, setFilename] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setError(null);
      const status = await getUserResume();
      setHasResume(status.has_resume);
      setFilename(status.filename ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail || e.message) : "Failed to load resume status");
      setHasResume(false);
      setFilename(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const refetch = useCallback(async () => {
    await fetchStatus();
    onResumeChange?.();
  }, [fetchStatus, onResumeChange]);

  const handleAddResumeFile = async () => {
    const file = resumeFile;
    if (!file || file.type !== "application/pdf") return;
    setUploading(true);
    setError(null);
    try {
      const { s3_key, upload_url } = await presignUserResume(file.name, file.size);
      await uploadToPresignedUrl(upload_url, file);
      await confirmUserResume(s3_key);
      setResumeFile(null);
      await refetch();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail || e.message) : "Failed to upload resume");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Remove your account resume? It will no longer be used for interview feedback.")) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteUserResume();
      await refetch();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail || e.message) : "Failed to delete resume");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="rounded-lg border border-white/20 bg-white/10">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium text-zenodrift-text transition-colors hover:bg-white/15"
        aria-expanded={expanded}
      >
        <span>Account Resume (applies to all job descriptions)</span>
        {hasResume && (
          <span className="rounded-full bg-white/30 px-2 py-0.5 text-xs text-zenodrift-text-muted">
            {filename ?? "Added"}
          </span>
        )}
        <svg
          className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-white/20 px-3 py-3">
          {error && (
            <p className="text-xs text-red-600" role="alert">
              {error}
            </p>
          )}
          {loading ? (
            <p className="text-xs text-zenodrift-text-muted">Loading…</p>
          ) : (
            <>
              <div className="flex gap-2">
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                  className="hidden"
                  id="account-resume-file"
                />
                <label
                  htmlFor="account-resume-file"
                  className="cursor-pointer rounded-lg border border-white/40 bg-white/60 px-2.5 py-1.5 text-xs text-zenodrift-text hover:bg-white/80"
                >
                  Upload PDF
                </label>
                {resumeFile && (
                  <button
                    onClick={handleAddResumeFile}
                    disabled={uploading}
                    className="rounded-lg bg-white/60 px-2.5 py-1.5 text-xs font-medium text-zenodrift-accent hover:bg-white/80 disabled:opacity-50"
                  >
                    {uploading ? "Uploading…" : "Add"}
                  </button>
                )}
              </div>
              {hasResume && (
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
                >
                  {deleting ? "Removing…" : "Remove resume"}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
