"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import {
  getMe,
  getPreferences,
  getStats,
  type Me,
  type Stats,
  type StoredPreference,
} from "@/lib/api";

export default function ProfilePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [prefs, setPrefs] = useState<StoredPreference[]>([]);

  useEffect(() => {
    getMe().then(setMe).catch(() => router.replace("/login"));
    getStats().then(setStats).catch(() => {});
    getPreferences().then(setPrefs).catch(() => {});
  }, [router]);

  if (!me) return null;

  return (
    <Shell me={me}>
      <div className="scroll">
        <div className="col">
          <div className="head">
            <div className="big">
              {(me.name ?? me.email).charAt(0).toUpperCase()}
            </div>
            <div>
              <h1>{me.name ?? me.email.split("@")[0]}</h1>
              <p className="sub">{me.email}</p>
            </div>
          </div>

          {stats && (
            <div className="figures">
              <div>
                <span className="n">{stats.conversations}</span>
                <span className="l">conversations</span>
              </div>
              <div>
                <span className="n">{stats.messages}</span>
                <span className="l">messages</span>
              </div>
              <div>
                <span className="n">{stats.preferences}</span>
                <span className="l">learned preferences</span>
              </div>
              <div>
                <span className="n">{me.connected_mailboxes.length}</span>
                <span className="l">mailboxes connected</span>
              </div>
            </div>
          )}

          <section>
            <h2>What PAAI has learned about you</h2>
            <p className="explain">
              Preferences picked up from how you phrase requests and correct
              results. Confidence rises when you repeat something and falls when
              a rule goes unused, so what you see here is what PAAI would
              actually apply right now.
            </p>

            {prefs.length === 0 ? (
              <p className="none">
                Nothing yet. Tell PAAI something like &ldquo;keep summaries
                short&rdquo; and it will remember.
              </p>
            ) : (
              <ul className="prefs">
                {prefs.map((p, i) => (
                  <li key={i}>
                    <div className="rule">
                      <span className="cat">{p.category}</span>
                      <span className="txt">{p.rule}</span>
                    </div>
                    <div className="meter" title={`confidence ${p.confidence}`}>
                      <div
                        className="fill"
                        style={{ width: `${p.confidence * 100}%` }}
                        data-strong={p.confidence >= 0.7}
                      />
                    </div>
                    <div className="meta">
                      <span>{p.scope}</span>
                      <span>{p.source}</span>
                      <span>seen {p.reinforcement_count}×</span>
                      <span>{Math.round(p.confidence * 100)}%</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>

      <style jsx>{`
        .scroll { flex: 1; overflow-y: auto; background: var(--panel); }
        .col { max-width: 50rem; margin: 0 auto; padding: 2.5rem 1.5rem 4rem; }
        .head { display: flex; align-items: center; gap: 1.25rem; }
        .big {
          display: grid; place-items: center;
          width: 72px; height: 72px; border-radius: 50%;
          background: var(--agent-wash); color: var(--agent);
          font-size: 1.8rem; font-weight: 600;
          border: 1px solid var(--rule);
        }
        h1 {
          font-family: var(--serif); font-weight: 400;
          font-size: 2.1rem; margin: 0;
        }
        .sub { margin: 0.15rem 0 0; color: var(--ink-soft); }

        .figures {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
          gap: 1px;
          margin: 2rem 0;
          background: var(--rule);
          border: 1px solid var(--rule);
          border-radius: 10px;
          overflow: hidden;
        }
        .figures > div {
          background: var(--paper);
          padding: 1rem 1.15rem;
        }
        .n {
          display: block;
          font-family: var(--serif);
          font-size: 2.1rem;
          line-height: 1.1;
        }
        .l { display: block; font-size: 0.92rem; color: var(--ink-soft); }

        section {
          background: var(--paper);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.5rem;
        }
        h2 { font-size: 1.12rem; font-weight: 600; margin: 0 0 0.4rem; }
        .explain {
          color: var(--ink-soft); font-size: 0.98rem;
          margin: 0 0 1.5rem; max-width: 42rem;
        }
        .none { color: var(--ink-faint); }

        .prefs { list-style: none; margin: 0; padding: 0; }
        .prefs li { padding: 1rem 0; border-top: 1px solid var(--rule-soft); }
        .prefs li:first-child { border-top: none; padding-top: 0; }
        .rule { display: flex; gap: 0.6rem; align-items: baseline; }
        .cat { color: var(--agent); font-size: 0.92rem; white-space: nowrap; }
        .txt { flex: 1; }
        .meter {
          height: 3px; background: var(--sunk);
          border-radius: 2px; margin: 0.6rem 0 0.4rem;
        }
        .fill { height: 100%; border-radius: 2px; background: var(--flag); }
        .fill[data-strong="true"] { background: var(--agent); }
        .meta {
          display: flex; gap: 1rem;
          font-size: 0.88rem; color: var(--ink-faint);
        }
      `}</style>
    </Shell>
  );
}
