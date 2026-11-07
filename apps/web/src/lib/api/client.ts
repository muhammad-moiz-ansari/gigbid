import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Generated paths enforce all endpoint inputs. CSRF lives in memory, never localStorage.
let csrf = "";
export function setCsrf(value: string) { csrf = value; }
export const api = createClient<paths>({ baseUrl: "/api", credentials: "include" });
api.use({ onRequest({ request }) {
  if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) request.headers.set("X-CSRF-Token", csrf);
  return request;
} });
export function checked<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.response.ok) {
    const error = result.error as { detail?: unknown } | undefined;
    throw new Error(typeof error?.detail === "string" ? error.detail : `Request failed (${result.response.status})`);
  }
  return result.data as T;
}
