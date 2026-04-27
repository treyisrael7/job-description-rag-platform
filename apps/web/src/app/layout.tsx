import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { AppChrome } from "@/components/AppChrome";
import { ClerkAuthProvider } from "@/components/ClerkAuthProvider";
import { ToastProvider } from "@/components/ui/ToastProvider";
import { LibraryProvider } from "@/contexts/LibraryContext";
import { QueryProvider } from "@/providers/QueryProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "InterviewOS",
  description: "Job description–grounded interview practice with evidence-cited feedback",
};

const clerkPublishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
const authMode = process.env.NEXT_PUBLIC_AUTH_MODE?.trim().toLowerCase();
const useClerk = Boolean(clerkPublishableKey && authMode === "clerk");

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const app = (
    <html lang="en">
      <body>
        <QueryProvider>
          <ToastProvider>
            <LibraryProvider>{children}</LibraryProvider>
          </ToastProvider>
        </QueryProvider>
      </body>
    </html>
  );

  if (!useClerk) {
    return app;
  }

  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          <ClerkAuthProvider>
            <QueryProvider>
              <ToastProvider>
                <LibraryProvider>
                  <AppChrome />
                  {children}
                </LibraryProvider>
              </ToastProvider>
            </QueryProvider>
          </ClerkAuthProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
