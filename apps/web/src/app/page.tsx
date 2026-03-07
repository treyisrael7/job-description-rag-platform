"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { useEffect } from "react";
import { GradientShell } from "@/components/GradientShell";

export default function LandingPage() {
  const { isSignedIn, isLoaded } = useUser();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.replace("/dashboard");
    }
  }, [isLoaded, isSignedIn, router]);

  if (isLoaded && isSignedIn) {
    return null; // Redirecting
  }

  return (
    <GradientShell>
      <section className="mx-auto flex max-w-[800px] flex-col items-center px-6 pb-16 pt-20 text-center sm:pt-28">
        <h1 className="relative inline-block pb-4 text-[clamp(2.5rem,6vw,3.75rem)] font-bold leading-[1.1] tracking-tighter text-zenodrift-text-strong">
          InterviewOS
          <span
            className="absolute bottom-0 left-1/2 h-1 w-16 -translate-x-1/2 rounded-full bg-gradient-to-r from-zenodrift-accent to-orange-400"
            aria-hidden
          />
        </h1>
        <p className="mt-6 max-w-[42ch] text-lg leading-relaxed text-zenodrift-text sm:text-xl">
          Job description–grounded interview practice with evidence-cited feedback.
          Upload a JD, add your resume, and practice with questions tailored to the role.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <span className="rounded-full border border-white/25 bg-white/20 px-4 py-2 text-sm font-medium text-zenodrift-text">
            Job description–grounded
          </span>
          <span className="rounded-full border border-white/25 bg-white/20 px-4 py-2 text-sm font-medium text-zenodrift-text">
            Evidence-cited
          </span>
          <span className="rounded-full border border-white/25 bg-white/20 px-4 py-2 text-sm font-medium text-zenodrift-text">
            Fast practice
          </span>
        </div>

        {/* Auth CTAs */}
        <div className="mt-12 flex flex-col items-center gap-4 sm:flex-row sm:gap-4">
          <Link
            href="/sign-up"
            className="w-full rounded-2xl bg-gradient-to-r from-orange-500 to-orange-600 px-8 py-4 text-base font-semibold text-white shadow-lg transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-zenodrift-accent focus:ring-offset-2 focus:ring-offset-transparent sm:w-auto"
          >
            Sign up free
          </Link>
          <Link
            href="/sign-in"
            className="w-full rounded-2xl border-2 border-white/40 bg-white/30 px-8 py-4 text-base font-semibold text-zenodrift-text-strong backdrop-blur-sm transition-all duration-200 hover:border-white/60 hover:bg-white/50 focus:outline-none focus:ring-2 focus:ring-zenodrift-accent/30 focus:ring-offset-2 focus:ring-offset-transparent sm:w-auto"
          >
            Sign in
          </Link>
        </div>
        <p className="mt-6 text-sm text-zenodrift-text-muted">
          Sign in to save your documents and sync across devices.
        </p>
      </section>
    </GradientShell>
  );
}
