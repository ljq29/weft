const API_BASE = "/api";

export class ApiError extends Error {
  readonly name = "ApiError";

  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly detail?: unknown,
    readonly response?: Response,
  ) {
    super(message);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function formatApiError(reason: unknown): string {
  if (reason instanceof ApiError) {
    const message = reason.message.trim() || `HTTP ${String(reason.status)}`;
    return `${message}（${reason.code}）`;
  }
  if (reason instanceof Error && reason.message) return reason.message;
  return "请求失败，请稍后重试";
}

export function sessionToken(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("token");
  if (fromUrl) {
    window.sessionStorage.setItem("weft-token", fromUrl);
    window.history.replaceState({}, "", window.location.pathname);
    return fromUrl;
  }
  return window.sessionStorage.getItem("weft-token") ?? "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${sessionToken()}`);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method === "PUT" || init.method === "PATCH")
    headers.set("X-Weft-Client", "ui");
  const response = await fetch(API_BASE + path, { ...init, headers });
  if (!response.ok) {
    const text = await response.text();
    let body: unknown;
    try {
      body = text ? (JSON.parse(text) as unknown) : undefined;
    } catch {
      body = undefined;
    }
    const payload =
      isRecord(body) && isRecord(body.error) ? body.error : undefined;
    const textMessage = body === undefined ? text.trim() : "";
    const message =
      nonEmptyString(payload?.message) ??
      (textMessage || `HTTP ${String(response.status)}`);
    const code =
      nonEmptyString(payload?.code) ?? `HTTP_${String(response.status)}`;
    throw new ApiError(
      response.status,
      code,
      message,
      payload?.detail,
      response,
    );
  }
  return response.json() as Promise<T>;
}
