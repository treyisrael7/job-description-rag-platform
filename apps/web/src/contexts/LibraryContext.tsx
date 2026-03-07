"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { LibraryModal } from "@/components/LibraryModal";

interface LibraryContextValue {
  openLibrary: () => void;
}

const LibraryContext = createContext<LibraryContextValue | null>(null);

export function useLibrary() {
  const ctx = useContext(LibraryContext);
  if (!ctx) throw new Error("useLibrary must be used within LibraryProvider");
  return ctx;
}

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const openLibrary = useCallback(() => setIsOpen(true), []);

  return (
    <LibraryContext.Provider value={{ openLibrary }}>
      {children}
      <LibraryModal isOpen={isOpen} onClose={() => setIsOpen(false)} />
    </LibraryContext.Provider>
  );
}
