/**
 * API client.
 *
 * Every request sends credentials so the browser attaches the httpOnly session
 * cookie. We never read the token in JS — that is what httpOnly is for, and why
 * nothing here touches localStorage.
 *
 * Access tokens last 15 minutes. A 401 triggers one refresh and one retry.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export class AuthError extends Error {}
export class MailboxRequiredError extends Error {
  constructor() {
    super("No mailbox connected");
  }
}
export class QuotaError extends Error {}
export type Usage = {
    used: number; limit: number; remaining: number | null; unlimited: boolean;
    used_last_7_days: number; cost_usd: number;
    by_purpose: { purpose: string; tokens: number; calls: number }[];
    by_model: { model: string; tokens: number; cost_usd: number }[];
  };

export const getUsage = () => request<Usage>("/usage");
let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  // Collapse concurrent 401s into one refresh — otherwise parallel requests
  // each rotate the refresh token and all but one lose the race.
  if (!refreshing) {
    refreshing = fetch(`${API}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((r) => r.ok)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const send = () =>
    fetch(`${API}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });

  let res = await send();

  if (res.status === 401) {
    if (await refreshSession()) res = await send();
    if (res.status === 401) throw new AuthError("Session expired");
  }
  if (res.status === 428) throw new MailboxRequiredError();
  if (res.status === 429) throw new QuotaError("Token limit reached");

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export type Me = {
  id: string;
  email: string;
  name: string | null;
  connected_mailboxes: string[];
  can_connect_google: boolean;
  is_owner: boolean;
  owner_email: string;
  pending_requests: number;
};

export const requestGoogleAccess = (note?: string) =>
  request<{ status: string; email: string; message: string }>(
    "/access/google/request",
    { method: "POST", body: JSON.stringify({ note: note ?? null }) }
  );

export type PlanStep = {
  agent: string;
  description: string;
  status: "done" | "running" | "retried" | "failed";
  note?: string;
};

export type AgentReply = {
  response: string;
  session_id: string;
  plan?: PlanStep[];
};

export type SessionSummary = {
  session_id: string;
  title: string;
  started_at: string;
  updated_at: string;
  message_count: number;
};

export type StoredMessage = {
  role: string;
  content: string;
  created_at: string;
};

export type Stats = {
  messages: number;
  conversations: number;
  preferences: number;
  first_seen: string | null;
};

export type StoredPreference = {
  category: string;
  rule: string;
  scope: string;
  confidence: number;
  source: string;
  reinforcement_count: number;
  updated_at: string;
};

// ── Calls ────────────────────────────────────────────────────────────────────
export const getMe = () => request<Me>("/auth/me");

export const askAgent = (query: string, sessionId?: string) =>
  request<AgentReply>("/agent", {
    method: "POST",
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });

export const listSessions = () =>
  request<{ sessions: SessionSummary[] }>("/sessions").then((r) => r.sessions);

export const getSession = (id: string) =>
  request<{ session_id: string; messages: StoredMessage[] }>(`/sessions/${id}`);

export const removeSession = (id: string) =>
  request(`/sessions/${id}`, { method: "DELETE" });

export const getStats = () => request<Stats>("/profile/stats");

export const getPreferences = () =>
  request<{ preferences: StoredPreference[] }>("/profile/preferences").then(
    (r) => r.preferences
  );

export const logout = () =>
  fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });

export const disconnectMailbox = (provider: string) =>
  request(`/connect/${provider}`, { method: "DELETE" });

// Full-page navigations: OAuth needs the browser to follow redirects.
export const loginUrl = (p: string) => `${API}/auth/${p}/login`;
export const connectUrl = (p: string) => `${API}/connect/${p}/start`;


export type TesterRequest = {
  email: string;
  status: string;
  name: string | null;
  note: string | null;
  requested_at: string | null;
  approved_at: string | null;
};

export const listTesterRequests = (status?: string) =>
  request<{ requests: TesterRequest[] }>(
    `/access/google/requests${status ? `?status=${status}` : ""}`
  ).then((r) => r.requests);

export const setTesterStatus = (email: string, status: string) =>
  request<{ email: string; status: string; reminder: string | null }>(
    "/access/google/status",
    { method: "POST", body: JSON.stringify({ email, status }) }
  );