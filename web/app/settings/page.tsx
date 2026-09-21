"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import {
  connectUrl,
  disconnectMailbox,
  getMe,
  logout,
  requestGoogleAccess,
  type Me,
} from "@/lib/api";

const PROVIDERS = [
  {
    id: "google",
    label: "Google",
    detail: "Gmail and Google Calendar",
  },
  {
    id: "microsoft",
    label: "Microsoft",
    detail: "Outlook mail and calendar",
  },
];

type RequestState = "idle" | "sending" | "sent" | "error";

export default function SettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [showGoogleNote, setShowGoogleNote] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [requestError, setRequestError] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => router.replace("/login"));
  }, [router]);

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
      // The endpoint is idempotent, so a second click on an existing request
      // returns the current status rather than erroring.
      setRequestState("sent");
      if (result.status === "approved") {
        // Approved between page load and clicking — refresh so the Connect
        // button appears without a manual reload.
        setMe(await getMe());
      }
    } catch (err) {
      setRequestState("error");
      setRequestError(
        err instanceof Error ? err.message : "Could not send the request."
      );
    }
  }

  if (!me) return null;

  return (
    <Shell me={me}>
      <div className="scroll">
        <div className="col">
          <h1>Settings</h1>

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
                    <p className="note-head">Request sent</p>
                    <p>
                      {me.owner_email || "The owner"} has been asked to approve
                      this address. Once approved, refresh this page and the
                      Connect button will work.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="note-head">Gmail needs approval first</p>
                    <p>
                      Google limits apps to an approved tester list until they
                      complete verification, so PAAI can&apos;t read your Gmail
                      yet. Request access and the owner can add you.
                    </p>
                  </>
                )}

                <p className="mono">{me.email}</p>

                {requestState !== "sent" && (
                  <div className="note-actions">
                    <button
                      className="primary"
                      onClick={submitRequest}
                      disabled={requestState === "sending"}
                    >
                      {requestState === "sending"
                        ? "Sending…"
                        : "Request access"}
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
        .scroll {
          flex: 1;
          overflow-y: auto;
          background: var(--panel);
        }
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
        }
        .explain {
          color: var(--ink-soft);
          font-size: 0.98rem;
          margin: 0 0 1.25rem;
          max-width: 40rem;
        }
        .row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 1rem;
          padding: 0.9rem 0;
        }
        .row + .row {
          border-top: 1px solid var(--rule-soft);
        }
        .label {
          display: block;
        }
        .detail {
          display: block;
          font-size: 0.92rem;
          color: var(--ink-soft);
        }
        .right {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .badge {
          font-size: 0.88rem;
          color: var(--agent);
          background: var(--agent-wash);
          padding: 0.2rem 0.55rem;
          border-radius: 999px;
        }
        .badge.pending {
          color: var(--flag);
          background: var(--flag-wash);
        }
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
        .quiet:hover {
          border-color: var(--agent);
          color: var(--agent);
        }

        .note {
          margin-top: 1rem;
          padding: 1.1rem 1.25rem;
          background: var(--flag-wash);
          border: 1px solid var(--rule);
          border-radius: 8px;
          font-size: 0.95rem;
        }
        .note p {
          margin: 0 0 0.75rem;
          color: var(--ink-soft);
        }
        .note-head {
          color: var(--ink) !important;
          font-weight: 600;
        }
        .mono {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.92rem;
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
        .primary {
          padding: 0.45rem 0.9rem;
          border: 1px solid var(--ink);
          border-radius: 6px;
          background: var(--ink);
          color: var(--paper);
          font-size: 0.98rem;
          white-space: nowrap;
        }
        .primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .error {
          color: var(--alert) !important;
          font-size: 0.9rem;
        }
        .aside {
          margin: 0 !important;
          font-size: 0.9rem;
          color: var(--ink-faint) !important;
        }
      `}</style>
    </Shell>
  );
}