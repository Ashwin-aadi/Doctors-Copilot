import { describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../auth";

describe("auth store", () => {
  it("holds the access token in memory only, never localStorage/sessionStorage", () => {
    const localSpy = vi.spyOn(Storage.prototype, "setItem");
    useAuthStore.getState().setSession({ id: "u1", email: "a@b.com", role: "patient", name: "A" }, "secret-token");

    expect(useAuthStore.getState().accessToken).toBe("secret-token");
    expect(localSpy).not.toHaveBeenCalled();
    localSpy.mockRestore();
  });

  it("clear() resets to anonymous", () => {
    useAuthStore.getState().setSession({ id: "u1", email: "a@b.com", role: "patient", name: "A" }, "tok");
    useAuthStore.getState().clear();

    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().status).toBe("anonymous");
  });
});
