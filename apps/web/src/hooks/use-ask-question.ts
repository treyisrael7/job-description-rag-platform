"use client";

import { useMutation } from "@tanstack/react-query";
import { ask } from "@/lib/api";
import { useUserResume } from "@/hooks/use-user-resume";

export function useAskQuestionMutation(documentId: string) {
  const { data: resume } = useUserResume();
  const resumeDocumentId =
    resume?.has_resume && resume.document_id ? resume.document_id : undefined;

  return useMutation({
    mutationFn: (question: string) =>
      ask(documentId, question, { resumeDocumentId }),
  });
}
