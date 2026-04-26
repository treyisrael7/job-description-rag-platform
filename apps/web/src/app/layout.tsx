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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
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
