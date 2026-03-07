"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";
import { setAuthTokenProvider } from "@/lib/auth";

/**
 * Syncs Clerk auth token to the API client.
 * Must be rendered inside ClerkProvider.
 */
export function ClerkAuthProvider({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth();

  useEffect(() => {
    setAuthTokenProvider(getToken);
  }, [getToken]);

  return <>{children}</>;
}
