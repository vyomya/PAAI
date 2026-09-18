"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import {
  connectUrl,
  disconnectMailbox,
  getMe,
  logout,
  type Me,
} from "@/lib/api";

const PROVIDERS = [
  { id: "google", label: "Google", detail: "Gmail and Google Calendar" },
  { id: "microsoft", label: "Microsoft", detail: "Outlook mail and calendar" },
];

export default function SettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => router.replace("/login"));
  }, [router]);

  async function signOut() {
    await logout();
    router.replace("/");
  }

  async function disconnect(provider: string) {
    await disconnectMailbox(provider);
    setMe(await getMe());
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
                  ) : (
                    <a className="quiet" href={connectUrl(p.id)}>
                      Connect
                    </a>
                  )}
                </div>
              );
            })}
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
        .scroll { flex: 1; overflow-y: auto; background: var(--panel); }
        .col { max-width: 44rem; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
        h1 {
          font-family: var(--serif); font-weight: 400;
          font-size: 2.1rem; margin: 0 0 2rem;
        }
        section {
          background: var(--paper);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.5rem;
          margin-bottom: 1.25rem;
        }
        h2 { font-size: 1.12rem; font-weight: 600; margin: 0 0 0.4rem; }
        .explain {
          color: var(--ink-soft); font-size: 0.98rem;
          margin: 0 0 1.25rem; max-width: 40rem;
        }
        .row {
          display: flex; justify-content: space-between;
          align-items: center; gap: 1rem; padding: 0.9rem 0;
        }
        .row + .row { border-top: 1px solid var(--rule-soft); }
        .label { display: block; }
        .detail { display: block; font-size: 0.92rem; color: var(--ink-soft); }
        .right { display: flex; align-items: center; gap: 0.75rem; }
        .badge {
          font-size: 0.88rem; color: var(--agent);
          background: var(--agent-wash);
          padding: 0.2rem 0.55rem; border-radius: 999px;
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
        .quiet:hover { border-color: var(--agent); color: var(--agent); }
      `}</style>
    </Shell>
  );
}
