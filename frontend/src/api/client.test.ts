import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, formatApiError } from "./client";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("window", {
    location: { search: "", pathname: "/" },
    history: { replaceState: vi.fn() },
    sessionStorage: {
      getItem: vi.fn(() => "session-token"),
      setItem: vi.fn(),
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("Expected API call to reject");
}

describe("API error contract", () => {
  it("US-DES-07/AC-4: preserves structured conflict errors for code-based handling", async () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "REVISION_CONFLICT",
          message: "工作流已被修改",
          detail: { expected: 2, actual: 3 },
        },
      }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );
    fetchMock.mockResolvedValue(response);

    const reason = await rejection(api("/workflows/wf_1"));

    expect(reason).toBeInstanceOf(ApiError);
    if (!(reason instanceof ApiError)) throw new Error("Expected ApiError");
    expect(reason.status).toBe(409);
    expect(reason.code).toBe("REVISION_CONFLICT");
    expect(reason.message).toBe("工作流已被修改");
    expect(reason.detail).toEqual({ expected: 2, actual: 3 });
    expect(reason.response).toBe(response);
  });

  it("US-EXE-07/AC-2: converts non-JSON error responses without losing HTTP context", async () => {
    const response = new Response("Bad Gateway", {
      status: 502,
      headers: { "Content-Type": "text/plain" },
    });
    fetchMock.mockResolvedValue(response);

    const reason = await rejection(api("/system/doctor"));

    expect(reason).toBeInstanceOf(ApiError);
    if (!(reason instanceof ApiError)) throw new Error("Expected ApiError");
    expect(reason).toMatchObject({
      status: 502,
      code: "HTTP_502",
      message: "Bad Gateway",
    });
    expect(reason.detail).toBeUndefined();
    expect(reason.response).toBe(response);
  });

  it("US-EXE-07/AC-2: formats visible messages while keeping stable codes available", () => {
    const conflict = new ApiError(409, "REVISION_CONFLICT", "保存冲突", {
      revision: 2,
    });

    expect(formatApiError(conflict)).toBe("保存冲突（REVISION_CONFLICT）");
    expect(formatApiError(new Error("磁盘只读"))).toBe("磁盘只读");
    expect(formatApiError(null)).toBe("请求失败，请稍后重试");
  });
});
