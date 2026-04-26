"use client";

import { useEffect, useState } from "react";

/**
 * Keeps a busy UI state visible for a minimum duration to avoid flicker.
 */
export function useDelayedBusy(isBusy: boolean, minBusyMs = 280): boolean {
  const [visibleBusy, setVisibleBusy] = useState(false);

  useEffect(() => {
    if (isBusy) {
      setVisibleBusy(true);
      return;
    }
    const timer = window.setTimeout(() => setVisibleBusy(false), minBusyMs);
    return () => window.clearTimeout(timer);
  }, [isBusy, minBusyMs]);

  return visibleBusy;
}
