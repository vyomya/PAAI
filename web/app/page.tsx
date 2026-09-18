"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, loginUrl } from "@/lib/api";

/**
 * Home. Signed in -> chat. Signed out -> a real landing page rather than an
 * instant redirect, so the URL is something you can share.
 */
export default function Home() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    getMe()
      .then(() => router.replace("/chat"))
      .catch(() => setChecking(false));
  }, [router]);

  if (checking) return null;

  return (
    <main className="page">
      <div className="col">
        <p className="mark">PAAI</p>

        <h1>
          Your inbox, read by an assistant that shows its working.
        </h1>

        <p className="lede">
          PAAI reads your mail and calendar, works out what actually needs your
          attention, and leaves a record of every step it took to get there.
        </p>

        <div className="actions">
          <a className="primary" href={loginUrl("google")}>
            Continue with Google
          </a>
          <a className="secondary" href={loginUrl("microsoft")}>
            Continue with Microsoft
          </a>
        </div>

        <ul className="points">
          <li>
            <span className="h">It learns how you work</span>
            Correct it once and it remembers. Rules you stop using fade out on
            their own.
          </li>
          <li>
            <span className="h">It checks itself</span>
            Every step is evaluated before the next one runs. When a result is
            wrong, it retries rather than handing you the mistake.
          </li>
          <li>
            <span className="h">It doesn&apos;t repeat work</span>
            Questions it has already answered are matched against past
            conversations instead of run again.
          </li>
        </ul>

        <p className="foot">
          Signing in shares your name and email. Your mailbox stays private
          until you connect it separately.
        </p>
      </div>

      <style jsx>{`
        .page {
          min-height: 100dvh;
          display: grid;
          place-items: center;
          padding: 3rem 1.5rem;
          background: var(--panel);
        }
        .col { width: 100%; max-width: 44rem; }
        .mark {
          font-family: var(--serif);
          font-size: 1.3rem;
          margin: 0 0 3rem;
        }
        h1 {
          font-family: var(--serif);
          font-weight: 400;
          font-size: clamp(2.1rem, 5.5vw, 3.2rem);
          line-height: 1.15;
          letter-spacing: -0.02em;
          margin: 0 0 1.25rem;
          max-width: 20ch;
        }
        .lede {
          font-size: 1.1rem;
          color: var(--ink-soft);
          max-width: 46ch;
          margin: 0 0 2.5rem;
        }
        .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
        .primary, .secondary {
          padding: 0.8rem 1.4rem;
          border-radius: 8px;
          text-decoration: none;
          font-weight: 500;
          border: 1px solid var(--ink);
        }
        .primary { background: var(--ink); color: var(--paper); }
        .secondary { background: var(--paper); color: var(--ink); border-color: var(--rule); }
        .secondary:hover { border-color: var(--ink); }

        .points {
          list-style: none;
          margin: 3.5rem 0 0;
          padding: 0;
          display: grid;
          gap: 1px;
          background: var(--rule);
          border: 1px solid var(--rule);
          border-radius: 10px;
          overflow: hidden;
        }
        .points li {
          background: var(--paper);
          padding: 1.15rem 1.3rem;
          font-size: 0.95rem;
          color: var(--ink-soft);
          max-width: none;
        }
        .h { display: block; color: var(--ink); margin-bottom: 0.2rem; }
        .foot {
          margin-top: 2rem;
          font-size: 0.875rem;
          color: var(--ink-faint);
        }
      `}</style>
    </main>
  );
}
