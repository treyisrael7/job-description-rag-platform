import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAuthToken, setAuthTokenProvider } from "./auth";

describe("auth", () => {
  beforeEach(() => {
    setAuthTokenProvider(() => Promise.resolve(null));
  });

  afterEach(() => {
    setAuthTokenProvider(() => Promise.resolve(null));
  });

  it("getAuthToken returns null when no provider set", async () => {
    setAuthTokenProvider(() => Promise.resolve(null));
    expect(await getAuthToken()).toBeNull();
  });

  it("getAuthToken returns token when provider returns token", async () => {
    setAuthTokenProvider(() => Promise.resolve("jwt-token-123"));
    expect(await getAuthToken()).toBe("jwt-token-123");
  });

  it("getAuthToken returns null when provider returns null", async () => {
    setAuthTokenProvider(() => Promise.resolve(null));
    expect(await getAuthToken()).toBeNull();
  });
});
