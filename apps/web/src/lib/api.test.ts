import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setAuthTokenProvider } from "./auth";

describe("api", () => {
  beforeEach(() => {
    setAuthTokenProvider(() => Promise.resolve(null));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("getAuthHeaders", () => {
    it("includes Bearer when token is present", async () => {
      setAuthTokenProvider(() => Promise.resolve("jwt-xyz"));
      const { getAuthHeaders } = await import("./api");
      const headers = await getAuthHeaders();
      const h = headers as Record<string, string>;
      expect(h["Authorization"]).toBe("Bearer jwt-xyz");
      expect(h["Content-Type"]).toBe("application/json");
    });

    it("omits Authorization when no token", async () => {
      setAuthTokenProvider(() => Promise.resolve(null));
      const { getAuthHeaders } = await import("./api");
      const headers = await getAuthHeaders();
      const h = headers as Record<string, string>;
      expect(h["Authorization"]).toBeUndefined();
      expect(h["Content-Type"]).toBe("application/json");
    });

    it("prefers Bearer when token present", async () => {
      setAuthTokenProvider(() => Promise.resolve("clerk-token"));
      const { getAuthHeaders } = await import("./api");
      const headers = await getAuthHeaders();
      const h = headers as Record<string, string>;
      expect(h["Authorization"]).toBe("Bearer clerk-token");
    });
  });

  describe("listDocuments", () => {
    it("includes user_id in query when no token (demo mode)", async () => {
      setAuthTokenProvider(() => Promise.resolve(null));
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify([])),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { listDocuments } = await import("./api");
      await listDocuments();

      expect(mockFetch).toHaveBeenCalledTimes(1);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain("user_id=11111111-1111-1111-1111-111111111111");
    });

    it("omits user_id from query when token present (Clerk mode)", async () => {
      setAuthTokenProvider(() => Promise.resolve("clerk-token"));
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify([])),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { listDocuments } = await import("./api");
      await listDocuments();

      const [url] = mockFetch.mock.calls[0];
      expect(url).not.toContain("user_id=");
    });

    it("returns parsed documents on success", async () => {
      const docs = [{ id: "1", filename: "a.pdf", status: "ready" }];
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(docs)),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { listDocuments } = await import("./api");
      const result = await listDocuments();

      expect(result).toEqual(docs);
    });
  });

  describe("ask", () => {
    it("includes user_id in body when no token", async () => {
      setAuthTokenProvider(() => Promise.resolve(null));
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ answer: "Yes", citations: [] })),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { ask } = await import("./api");
      await ask("doc-123", "What is the salary?");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/ask"),
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("doc-123"),
        })
      );
      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.user_id).toBe("11111111-1111-1111-1111-111111111111");
      expect(body.document_id).toBe("doc-123");
      expect(body.question).toBe("What is the salary?");
    });

    it("omits user_id from body when token present", async () => {
      setAuthTokenProvider(() => Promise.resolve("clerk-token"));
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ answer: "Yes", citations: [] })),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { ask } = await import("./api");
      await ask("doc-123", "What?");

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.user_id).toBeUndefined();
    });
  });

  describe("ApiError", () => {
    it("throws ApiError with status and detail on non-OK response", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: "Not Found",
        text: () => Promise.resolve(JSON.stringify({ detail: "Document not found" })),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { getDocument } = await import("./api");

      try {
        await getDocument("missing-id");
        expect.fail("Should have thrown");
      } catch (e) {
        expect((e as Error).name).toBe("ApiError");
        expect((e as { status: number; detail?: unknown }).status).toBe(404);
        expect((e as { status: number; detail?: unknown }).detail).toBe("Document not found");
      }
    });

    it("preserves detail from JSON detail field", async () => {
      const mockFetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        text: () => Promise.resolve(JSON.stringify({ detail: "Authentication required" })),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { listDocuments } = await import("./api");

      try {
        await listDocuments();
        expect.fail("Should have thrown");
      } catch (e) {
        expect((e as Error).name).toBe("ApiError");
        expect((e as { detail?: unknown }).detail).toBe("Authentication required");
      }
    });
  });

  describe("presign", () => {
    it("sends user_id in body when no token", async () => {
      setAuthTokenProvider(() => Promise.resolve(null));
      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        text: () =>
          Promise.resolve(
            JSON.stringify({
              document_id: "d1",
              s3_key: "k1",
              upload_url: "/upload",
              method: "PUT",
            })
          ),
      });
      vi.stubGlobal("fetch", mockFetch);

      const { presign } = await import("./api");
      await presign("test.pdf", 1024);

      const body = JSON.parse(mockFetch.mock.calls[0][1].body);
      expect(body.user_id).toBe("11111111-1111-1111-1111-111111111111");
      expect(body.filename).toBe("test.pdf");
      expect(body.file_size_bytes).toBe(1024);
    });
  });
});
