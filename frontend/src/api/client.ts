const API_BASE = "/api";

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
    const body = (await response.json()) as { error?: { message?: string } };
    throw new Error(body.error?.message ?? `HTTP ${String(response.status)}`);
  }
  return response.json() as Promise<T>;
}
