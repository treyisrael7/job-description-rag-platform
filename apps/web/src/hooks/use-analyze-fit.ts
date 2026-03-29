"use client";

import { useMutation } from "@tanstack/react-query";
import { analyzeFit } from "@/lib/api";
import { useUserResume } from "@/hooks/use-user-resume";

export function useAnalyzeFitMutation(jobDescriptionId: string) {
  const { data: resume } = useUserResume();
  const resumeId =
    resume?.has_resume && resume.document_id ? resume.document_id : null;

  return useMutation({
    mutationFn: async (opts?: { question?: string }) => {
      if (!resumeId) {
        throw new Error("RESUME_REQUIRED");
      }
      return analyzeFit({
        jobDescriptionId,
        resumeId,
        question: opts?.question,
      });
    },
  });
}
