"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import {
  connectUrl,
  disconnectMailbox,
  getMe,
  listTesterRequests,
  logout,
  requestGoogleAccess,
  setTesterStatus,
  type Me,
  type TesterRequest,
} from "@/lib/api";

const PROVIDERS = [
  { id: "google", label: "Google", detail: "Gmail and Google Calendar" },
  { id: "microsoft", label: "Microsoft", detail: "Outlook mail and calendar" },
];

type RequestState = "idle" | "sending" | "sent" | "error";

export default function SettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [showGoogleNote, setShowGoogleNote] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [requestError, setRequestError] = useState<string | null>(null);

  // Owner-only
  const [testers, setTesters] = useState<TesterRequest[]>([]);
  const [acting, setActing] = useState<string | null>(null);
  const [reminder, setReminder] = useState<string | null>(null);

  const refreshTesters = useCallback(() => {
    listTesterRequests()
      .then(setTesters)
      .catch(() => {});
  }, []);

  useEffect(() => {
    getMe()
      .then((m) => {
        setMe(m);
        if (m.is_owner) refreshTesters();
      })
      .catch(() => router.replace("/login"));
  }, [router, refreshTesters]);

  async function signOut() {
    await logout();
    router.replace("/");
  }

  async function disconnect(provider: string) {
    await disconnectMailbox(provider);
    setMe(await getMe());
  }

  async function submitRequest() {
    setRequestState("sending");
    setRequestError(null);
    try {
      const result = await requestGoogleAccess();
      setRequestState("sent");
      if (result.status === "approved") setMe(await getMe());
    } catch (err) {
      setRequestState("error");
      setRequestError(
        err instanceof Error ? err.message : "Could not send the request."
      );
    }
  }

  async function decide(email: string, status: "approved" | "denied") {
    setActing(email);
    try {
      const result = await setTesterStatus(email, status);
      setReminder(result.reminder ?? null);
      refreshTesters();
      setMe(await getMe());
    } finally {
      setActing(null);
    }
  }

  if (!me) return null;

  const pending = testers.filter((t) => t.status === "pending");
  const decided = testers.filter((t) => t.status !== "pending");

  return (
    <Shell me={me}>
      <div className="scroll">
        <div className="col">
          <h1>Settings</h1>

          {/* ── Owner: tester queue ─────────────────────────────────────── */}
          {me.is_owner && (
            <section>
              <h2>
                Tester requests
                {pending.length > 0 && (
                  <span className="count">{pending.length}</span>
                )}
              </h2>
              <p className="explain">
                Approving here unlocks the Connect button in PAAI. You must{" "}
                <strong>also</strong> add the address under Google Auth
                Platform → Audience → Test users, or Google will still refuse
                the consent.
              </p>

              {reminder && <p className="reminder">{reminder}</p>}

              {pending.length === 0 && decided.length === 0 && (
                <p className="none">No requests yet.</p>
              )}

              {pending.map((t) => (
                <div className="row" key={t.email}>
                  <span>
                    <span className="label">{t.name || t.email}</span>
                    <span className="detail mono">{t.email}</span>
                    {t.requested_at && (
                      <span className="detail">
                        asked{" "}
                        {new Date(t.requested_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    )}
                  </span>
                  <span className="right">
                    <button
                      className="primary"
                      disabled={acting === t.email}
                      onClick={() => decide(t.email, "approved")}
                    >
                      Approve
                    </button>
                    <button
                      className="quiet"
                      disabled={acting === t.email}
                      onClick={() => decide(t.email, "denied")}
                    >
                      Deny
                    </button>
                  </span>
                </div>
              ))}

              {decided.length > 0 && (
                <details className="decided">
                  <summary>{decided.length} already handled</summary>
                  {decided.map((t) => (
                    <div className="row" key={t.email}>
                      <span>
                        <span className="label">{t.name || t.email}</span>
                        <span className="detail mono">{t.email}</span>
                      </span>
                      <span className="right">
                        <span
                          className={
                            t.status === "approved" ? "badge" : "badge denied"
                          }
                        >
                          {t.status}
                        </span>
                        {t.status !== "approved" && (
                          <button
                            className="quiet"
                            disabled={acting === t.email}
                            onClick={() => decide(t.email, "approved")}
                          >
                            Approve
                          </button>
                        )}
                      </span>
                    </div>
                  ))}
                </details>
              )}
            </section>
          )}

          {/* ── Mailboxes ───────────────────────────────────────────────── */}
          <section>
            <h2>Mailboxes</h2>
            <p className="explain">
              PAAI reads mail and calendar only for accounts connected here.
              Disconnect and it loses access immediately.
            </p>

            {PROVIDERS.map((p) => {
              const connected = me.connected_mailboxes.includes(p.id);
              const blocked = p.id === "google" && !me.can_connect_google;

              return (
                <div className="row" key={p.id}>
                  <span>
                    <span className="label">{p.label}</span>
                    <span className="detail">{p.detail}</span>
                  </span>

                  {connected ? (
                    <span className="right">
                      <span className="badge">Connected</span>
                      <button className="quiet" onClick={() => disconnect(p.id)}>
                        Disconnect
                      </button>
                    </span>
                  ) : blocked ? (
                    <span className="right">
                      {requestState === "sent" && (
                        <span className="badge pending">Requested</span>
                      )}
                      <button
                        className="quiet"
                        onClick={() => setShowGoogleNote((v) => !v)}
                      >
                        {requestState === "sent" ? "Details" : "Request access"}
                      </button>
                    </span>
                  ) : (
                    <a className="quiet" href={connectUrl(p.id)}>
                      Connect
                    </a>
                  )}
                </div>
              );
            })}

            {showGoogleNote && (
              <div className="note">
                {requestState === "sent" ? (
                  <>
                    <p className="note-head">Request recorded</p>
                    <p>
                      Your address is on the approval list. Once approved,
                      refresh this page and Connect will work.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="note-head">Gmail needs approval first</p>
                    <p>
                      Google limits apps to an approved tester list until they
                      complete verification, so PAAI can&apos;t read your Gmail
                      yet.
                    </p>
                  </>
                )}

                <p className="mono box">{me.email}</p>

                {requestState !== "sent" && (
                  <div className="note-actions">
                    <button
                      className="primary"
                      onClick={submitRequest}
                      disabled={requestState === "sending"}
                    >
                      {requestState === "sending" ? "Sending…" : "Request access"}
                    </button>
                  </div>
                )}

                {requestState === "error" && (
                  <p className="error">{requestError}</p>
                )}

                <p className="aside">
                  Outlook has no such restriction — you can connect a Microsoft
                  account right now.
                </p>
              </div>
            )}
          </section>

          {/* ── Account ─────────────────────────────────────────────────── */}
          <section>
            <h2>Account</h2>
            <div className="row">
              <span>
                <span className="label">{me.email}</span>
                <span className="detail">Signed in</span>
              </span>
              <button className="quiet" onClick={signOut}>
                Sign out
              </button>
            </div>
          </section>
        </div>
      </div>

      <style jsx>{`
        .scroll { flex: 1; overflow-y: auto; background: var(--panel); }
        .col {
          max-width: 44rem;
          margin: 0 auto;
          padding: 2.5rem 1.5rem 4rem;
        }
        h1 {
          font-family: var(--serif);
          font-weight: 400;
          font-size: 2.1rem;
          margin: 0 0 2rem;
        }
        section {
          background: var(--paper);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.5rem;
          margin-bottom: 1.25rem;
        }
        h2 {
          font-size: 1.12rem;
          font-weight: 600;
          margin: 0 0 0.4rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .count {
          display: inline-grid;
          place-items: center;
          min-width: 20px;
          height: 20px;
          padding: 0 6px;
          border-radius: 999px;
          background: var(--flag);
          color: var(--paper);
          font-size: 0.75rem;
        }
        .explain {
          color: var(--ink-soft);
          font-size: 0.98rem;
          margin: 0 0 1.25rem;
          max-width: 40rem;
        }
        .reminder {
          margin: 0 0 1rem;
          padding: 0.7rem 0.9rem;
          background: var(--flag-wash);
          border-radius: 6px;
          font-size: 0.92rem;
          color: var(--ink-soft);
        }
        .none { color: var(--ink-faint); margin: 0; }

        .row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          padding: 0.9rem 0;
        }
        .row + .row { border-top: 1px solid var(--rule-soft); }
        .label { display: block; }
        .detail {
          display: block;
          font-size: 0.92rem;
          color: var(--ink-soft);
        }
        .right { display: flex; align-items: center; gap: 0.6rem; }

        .badge {
          font-size: 0.88rem;
          color: var(--agent);
          background: var(--agent-wash);
          padding: 0.2rem 0.55rem;
          border-radius: 999px;
        }
        .badge.pending { color: var(--flag); background: var(--flag-wash); }
        .badge.denied { color: var(--ink-faint); background: var(--sunk); }

        .quiet {
          padding: 0.45rem 0.9rem;
          border: 1px solid var(--rule);
          border-radius: 6px;
          background: transparent;
          color: var(--ink);
          font-size: 0.98rem;
          text-decoration: none;
          white-space: nowrap;
        }
        .quiet:hover:not(:disabled) {
          border-color: var(--agent);
          color: var(--agent);
        }
        .primary {
          padding: 0.45rem 0.9rem;
          border: 1px solid var(--ink);
          border-radius: 6px;
          background: var(--ink);
          color: var(--paper);
          font-size: 0.98rem;
          white-space: nowrap;
        }
        .primary:disabled, .quiet:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }

        .decided {
          margin-top: 1rem;
          border-top: 1px solid var(--rule);
          padding-top: 0.75rem;
        }
        .decided summary {
          cursor: pointer;
          font-size: 0.92rem;
          color: var(--ink-soft);
        }

        .note {
          margin-top: 1rem;
          padding: 1.1rem 1.25rem;
          background: var(--flag-wash);
          border: 1px solid var(--rule);
          border-radius: 8px;
          font-size: 0.95rem;
        }
        .note p { margin: 0 0 0.75rem; color: var(--ink-soft); }
        .note-head { color: var(--ink) !important; font-weight: 600; }
        .mono {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.9rem;
        }
        .box {
          color: var(--ink) !important;
          background: var(--paper);
          border: 1px solid var(--rule);
          border-radius: 6px;
          padding: 0.5rem 0.7rem;
          word-break: break-all;
        }
        .note-actions {
          display: flex;
          gap: 0.6rem;
          flex-wrap: wrap;
          margin-bottom: 0.75rem;
        }
        .error { color: var(--alert) !important; font-size: 0.9rem; }
        .aside {
          margin: 0 !important;
          font-size: 0.9rem;
          color: var(--ink-faint) !important;
        }
      `}</style>
    </Shell>
  );
}