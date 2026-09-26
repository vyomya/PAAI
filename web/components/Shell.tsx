"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Me } from "@/lib/api";

/**
 * Shared chrome. One nav across chat, profile and settings so navigating
 * between them feels like moving inside one app rather than between pages.
 */
export default function Shell({
  me,
  children,
  sidebar,
}: {
  me: Me;
  children: React.ReactNode;
  sidebar?: React.ReactNode;
}) {
  const path = usePathname();
  const initial = (me.name ?? me.email).charAt(0).toUpperCase();

  return (
    <div className="shell">
      <header>
        <Link href="/chat" className="mark">
          PAAI
        </Link>

        <nav>
          <Link href="/chat" data-active={path.startsWith("/chat")}>
            Chat
          </Link>
          <Link href="/profile" data-active={path.startsWith("/profile")}>
            Profile
          </Link>
          <Link href="/settings" data-active={path.startsWith("/settings")}>
            Settings
            {me.pending_requests > 0 && (
              <span className="pip">{me.pending_requests}</span>
            )}
          </Link>
        </nav>

        <Link href="/profile" className="avatar" title={me.email}>
          {initial}
        </Link>
      </header>

      <div className="frame">
        {sidebar && <div className="rail">{sidebar}</div>}
        <div className="content">{children}</div>
      </div>

      <style jsx>{`
        .shell {
          display: flex;
          flex-direction: column;
          height: 100dvh;
        }
        header {
          flex: none;
          display: flex;
          align-items: center;
          gap: 2rem;
          padding: 0 1.25rem;
          height: 64px;
          background: var(--paper);
          border-bottom: 1px solid var(--rule);
        }
        .mark {
          font-family: var(--serif);
          font-size: 1.35rem;
          text-decoration: none;
          letter-spacing: -0.01em;
        }
        nav {
          display: flex;
          gap: 1.5rem;
          flex: 1;
        }
        nav :global(a) {
          font-size: 1rem;
          color: var(--ink-soft);
          text-decoration: none;
          padding: 0.25rem 0;
          border-bottom: 2px solid transparent;
        }
        nav :global(a[data-active="true"]) {
          color: var(--ink);
          border-bottom-color: var(--agent);
        }
        nav :global(a:hover) {
          color: var(--ink);
        }
        nav :global(.pip) {
          display: inline-grid;
          place-items: center;
          min-width: 18px;
          height: 18px;
          margin-left: 0.4rem;
          padding: 0 5px;
          border-radius: 999px;
          background: var(--flag);
          color: var(--paper);
          font-size: 0.72rem;
          font-weight: 600;
          vertical-align: middle;
        }
        .avatar {
          display: grid;
          place-items: center;
          width: 38px;
          height: 38px;
          border-radius: 50%;
          background: var(--agent-wash);
          color: var(--agent);
          font-weight: 600;
          font-size: 0.95rem;
          text-decoration: none;
          border: 1px solid var(--rule);
        }
        .frame {
          flex: 1;
          display: flex;
          min-height: 0;
        }
        .rail {
          flex: none;
          width: var(--rail);
          background: var(--panel);
          border-right: 1px solid var(--rule);
          overflow-y: auto;
        }
        .content {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          background: var(--paper);
        }
        @media (max-width: 1000px) {
          .rail {
            display: none;
          }
          header {
            gap: 1.25rem;
          }
          nav {
            gap: 1rem;
          }
        }
      `}</style>
    </div>
  );
}
