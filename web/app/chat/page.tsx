"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Shell from "@/components/Shell";
import Markdown from "@/components/Markdown";
import {
  AuthError,
  MailboxRequiredError,
  QuotaError,
  askAgent,
  getMe,
  getSession,
  getUsage,
  listSessions,
  removeSession,
  type Me,
  type PlanStep,
  type SessionSummary,
  type Usage,
} from "@/lib/api";

type Turn = { role: "you" | "assistant"; text: string; plan?: PlanStep[] };

// Warn once the balance drops below this fraction of the limit, so the cutoff
// is never a surprise mid-conversation.
const LOW_QUOTA = 0.15;

function ChatInner() {
  const router = useRouter();
  const params = useSearchParams();
  const urlSession = params.get("s") ?? undefined;

  const [me, setMe] = useState<Me | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(urlSession);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [quotaBlocked, setQuotaBlocked] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => router.replace("/login"));
  }, [router]);

  const refreshSessions = useCallback(() => {
    listSessions().then(setSessions).catch(() => {});
  }, []);

  const refreshUsage = useCallback(() => {
    getUsage()
      .then((u) => {
        setUsage(u);
        // Unblock automatically if the owner raised the limit.
        if (!u.unlimited && u.remaining !== null && u.remaining > 0) {
          setQuotaBlocked(false);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (me) {
      refreshSessions();
      refreshUsage();
    }
  }, [me, refreshSessions, refreshUsage]);

  // Load a conversation from the server whenever the URL points at one.
  // This is what makes navigating to settings and back non-destructive:
  // the conversation lives in Postgres, not in component state.
  useEffect(() => {
    if (!urlSession) {
      setTurns([]);
      setSessionId(undefined);
      return;
    }
    getSession(urlSession)
      .then((s) => {
        setSessionId(s.session_id);
        setTurns(
          s.messages.map((m) => ({
            role: m.role === "user" ? "you" : "assistant",
            text: m.content,
          }))
        );
      })
      .catch(() => router.replace("/chat"));
  }, [urlSession, router]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  function autosize() {
    const el = boxRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  async function send(text?: string) {
    const query = (text ?? draft).trim();
    if (!query || busy || quotaBlocked) return;

    setDraft("");
    setError(null);
    setTurns((t) => [...t, { role: "you", text: query }]);
    setBusy(true);
    requestAnimationFrame(autosize);

    try {
      const reply = await askAgent(query, sessionId);
      setSessionId(reply.session_id);
      if (!urlSession) {
        router.replace(`/chat?s=${reply.session_id}`, { scroll: false });
      }
      setTurns((t) => [
        ...t,
        { role: "assistant", text: reply.response, plan: reply.plan },
      ]);
      refreshSessions();
      // A turn can cost a lot, so re-read rather than estimating client-side.
      refreshUsage();
    } catch (err) {
      if (err instanceof AuthError) return router.replace("/login");

      if (err instanceof QuotaError) {
        setQuotaBlocked(true);
        // Drop the optimistic user turn — it never ran, and leaving it there
        // implies an answer is coming.
        setTurns((t) => t.slice(0, -1));
        setDraft(query);
        refreshUsage();
        return;
      }
      setError(
        err instanceof MailboxRequiredError
          ? "Connect a mailbox in settings before asking about email."
          : err instanceof Error
          ? err.message
          : "Something went wrong."
      );
    } finally {
      setBusy(false);
    }
  }

  async function drop(id: string) {
    await removeSession(id);
    refreshSessions();
    if (id === sessionId) router.replace("/chat");
  }

  if (!me) return null;
  const noMailbox = me.connected_mailboxes.length === 0;

  const lowQuota =
    usage &&
    !usage.unlimited &&
    usage.remaining !== null &&
    usage.remaining > 0 &&
    usage.remaining < usage.limit * LOW_QUOTA;

  const rail = (
    <div className="rail-inner">
      <button className="new" onClick={() => router.push("/chat")}>
        New conversation
      </button>

      {sessions.length === 0 ? (
        <p className="rail-empty">Conversations you start appear here.</p>
      ) : (
        <ul>
          {sessions.map((s) => (
            <li key={s.session_id} data-current={s.session_id === sessionId}>
              <a
                href={`/chat?s=${s.session_id}`}
                onClick={(e) => {
                  e.preventDefault();
                  router.push(`/chat?s=${s.session_id}`);
                }}
              >
                <span className="t">{s.title}</span>
                <span className="m">
                  {new Date(s.updated_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })}
                  {" · "}
                  {s.message_count}
                </span>
              </a>
              <button
                className="x"
                onClick={() => drop(s.session_id)}
                aria-label={`Delete ${s.title}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {usage && !usage.unlimited && (
        <div className="quota">
          <div className="quota-bar">
            <div
              className="quota-fill"
              style={{
                width: `${Math.min(100, (usage.used / usage.limit) * 100)}%`,
              }}
              data-low={Boolean(lowQuota)}
            />
          </div>
          <p className="quota-text">
            {usage.used.toLocaleString()} of {usage.limit.toLocaleString()}{" "}
            tokens
          </p>
        </div>
      )}

      <style jsx>{`
        .rail-inner {
          padding: 1.1rem 0.9rem;
          display: flex;
          flex-direction: column;
          min-height: 100%;
        }
        .new {
          width: 100%;
          padding: 0.7rem;
          margin-bottom: 1.1rem;
          border: 1px solid var(--rule);
          background: var(--paper);
          color: var(--ink);
          font-size: 1rem;
          border-radius: 6px;
        }
        .new:hover { border-color: var(--agent); color: var(--agent); }
        .rail-empty {
          font-size: 0.95rem;
          color: var(--ink-faint);
          padding: 0 0.25rem;
        }
        ul { list-style: none; margin: 0; padding: 0; flex: 1; }
        li {
          display: flex;
          align-items: center;
          border-radius: 6px;
        }
        li:hover { background: var(--sunk); }
        li[data-current="true"] { background: var(--agent-wash); }
        li :global(a) {
          flex: 1;
          min-width: 0;
          display: block;
          padding: 0.6rem 0.6rem;
          text-decoration: none;
        }
        .t {
          display: block;
          font-size: 1rem;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .m { display: block; font-size: 0.85rem; color: var(--ink-faint); }
        .x {
          border: none;
          background: none;
          color: var(--ink-faint);
          font-size: 1.1rem;
          padding: 0 0.5rem;
          opacity: 0;
        }
        li:hover .x { opacity: 1; }
        .x:hover { color: var(--alert); }

        .quota {
          margin-top: auto;
          padding: 0.9rem 0.6rem 0.2rem;
          border-top: 1px solid var(--rule);
        }
        .quota-bar {
          height: 4px;
          background: var(--sunk);
          border-radius: 2px;
          overflow: hidden;
        }
        .quota-fill {
          height: 100%;
          background: var(--agent);
          border-radius: 2px;
          transition: width 0.3s;
        }
        .quota-fill[data-low="true"] { background: var(--flag); }
        .quota-text {
          margin: 0.45rem 0 0;
          font-size: 0.82rem;
          color: var(--ink-faint);
        }
      `}</style>
    </div>
  );

  return (
    <Shell me={me} sidebar={rail}>
      {noMailbox && (
        <div className="banner">
          No mailbox connected. <a href="/settings">Connect one</a> to ask about
          email or calendar.
        </div>
      )}

      {quotaBlocked ? (
        <div className="banner alert">
          You&apos;ve used your full token allowance. Ask{" "}
          {me.owner_email || "the owner"} to raise your limit to keep going.
        </div>
      ) : (
        lowQuota && (
          <div className="banner">
            {usage!.remaining!.toLocaleString()} tokens left — roughly a handful
            more questions.
          </div>
        )
      )}

      <div className="stream">
        <div className="col">
          {turns.length === 0 && !busy && (
            <div className="empty">
              <h1>What needs doing?</h1>
              <p>PAAI reads your inbox and shows every step it took.</p>
              <div className="starters">
                {[
                  "Summarise the last ten emails I received",
                  "What are my free slots next week?",
                  "Don't put newsletters in my to-do list",
                ].map((s) => (
                  <button key={s} onClick={() => send(s)} disabled={quotaBlocked}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn, i) => (
            <article
              key={i}
              className={turn.role}
              data-ledger={Boolean(turn.plan && turn.plan.length > 0)}
            >
              <div className="body">
                <p className="who">{turn.role === "you" ? "You" : "PAAI"}</p>
                <div className="text">
                  {turn.role === "assistant" ? (
                    <Markdown>{turn.text}</Markdown>
                  ) : (
                    turn.text
                  )}
                </div>
              </div>

              {turn.plan && turn.plan.length > 0 && (
                <aside className="ledger">
                  <p className="ledger-head">How it got there</p>
                  <ol>
                    {turn.plan.map((step, j) => (
                      <li key={j} data-status={step.status}>
                        <span className="agent">{step.agent}</span>
                        <span className="desc">{step.description}</span>
                        {step.note && <span className="note">{step.note}</span>}
                      </li>
                    ))}
                  </ol>
                </aside>
              )}
            </article>
          ))}

          {busy && (
            <article className="assistant">
              <div className="body">
                <p className="who">PAAI</p>
                <div className="working">Working through it…</div>
              </div>
            </article>
          )}

          {error && <p className="error">{error}</p>}
          <div ref={endRef} />
        </div>
      </div>

      <div className="composer">
        <div className="composer-inner">
          <textarea
            ref={boxRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              autosize();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              quotaBlocked
                ? "Token limit reached"
                : "Ask about your inbox…"
            }
            rows={1}
            disabled={busy || quotaBlocked}
          />
          <button
            onClick={() => send()}
            disabled={busy || quotaBlocked || !draft.trim()}
          >
            Send
          </button>
        </div>
      </div>

      <style jsx>{`
        .banner {
          flex: none;
          padding: 0.8rem 2rem;
          background: var(--flag-wash);
          border-bottom: 1px solid var(--rule);
          font-size: 0.98rem;
        }
        .banner.alert {
          background: var(--paper);
          border-bottom-color: var(--alert);
          color: var(--alert);
        }
        .stream {
          flex: 1;
          overflow-y: auto;
          background: var(--panel);
        }
        .col {
          /* Wide enough that a message plus its ledger both breathe, capped so
             prose never runs past a comfortable measure on an ultrawide. */
          max-width: 82rem;
          margin: 0 auto;
          padding: 2.25rem 2rem 1rem;
        }
        .empty { padding: 3rem 0; max-width: 34rem; }
        .empty h1 {
          font-family: var(--serif);
          font-weight: 400;
          font-size: 2.3rem;
          margin: 0 0 0.5rem;
        }
        .empty p { color: var(--ink-soft); margin: 0 0 1.75rem; }
        .starters { display: flex; flex-direction: column; gap: 0.5rem; }
        .starters button {
          text-align: left;
          padding: 0.7rem 0.9rem;
          border: 1px solid var(--rule);
          background: var(--paper);
          color: var(--ink);
          border-radius: 8px;
          font-size: 1rem;
        }
        .starters button:hover:not(:disabled) {
          border-color: var(--agent);
          color: var(--agent);
        }
        .starters button:disabled { opacity: 0.4; cursor: not-allowed; }

        article {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          gap: 1.75rem;
          margin-bottom: 1rem;
        }
        /* Only reserve the ledger column when there is a ledger. Reserving it
           unconditionally squeezed every message into two-thirds of the row. */
        article[data-ledger="true"] {
          grid-template-columns: minmax(0, 1fr) 17rem;
        }
        .body {
          min-width: 0;
          background: var(--raised);
          border: 1px solid var(--rule);
          border-radius: 10px;
          padding: 1.25rem 1.5rem;
        }
        .you .body { background: var(--sunk); border-color: transparent; }
        .who {
          margin: 0 0 0.45rem;
          font-size: 0.85rem;
          color: var(--ink-faint);
        }
        .text {
          white-space: pre-wrap;
          /* Long unbroken strings (calendar URLs, message ids) must wrap or
             they force the whole column wider than the viewport. */
          overflow-wrap: anywhere;
        }
        .assistant .text {
          white-space: normal;
          font-family: var(--serif);
          font-size: 1.12rem;
          line-height: 1.72;
        }
        .working { font-family: var(--serif); color: var(--ink-soft); font-style: italic; }

        .ledger { font-size: 0.9rem; padding-top: 0.25rem; min-width: 0; }
        .ledger-head { margin: 0 0 0.5rem; color: var(--ink-faint); }
        .ledger ol {
          list-style: none; margin: 0; padding: 0;
          border-left: 1px solid var(--rule);
        }
        .ledger li {
          padding: 0.4rem 0 0.4rem 0.8rem;
          margin-left: -1px;
          border-left: 2px solid transparent;
          display: flex; flex-direction: column; gap: 0.1rem;
        }
        .ledger li[data-status="done"] { border-left-color: var(--agent); }
        .ledger li[data-status="retried"] { border-left-color: var(--flag); }
        .ledger li[data-status="failed"] { border-left-color: var(--alert); }
        .agent { color: var(--agent); }
        .desc { color: var(--ink-soft); }
        .ledger .note { color: var(--flag); }
        .error { color: var(--alert); }

        .composer {
          flex: none;
          border-top: 1px solid var(--rule);
          background: var(--paper);
          padding: 0.9rem 1.5rem;
        }
        .composer-inner {
          max-width: 82rem;
          margin: 0 auto;
          display: flex;
          gap: 0.75rem;
          align-items: flex-end;
        }
        textarea {
          flex: 1;
          resize: none;
          padding: 0.8rem 1rem;
          border: 1px solid var(--rule);
          border-radius: 8px;
          background: var(--paper);
          color: var(--ink);
          font-family: var(--sans);
          font-size: 1.05rem;
          line-height: 1.5;
        }
        textarea:focus { border-color: var(--agent); }
        textarea:disabled { opacity: 0.6; }
        .composer button {
          padding: 0.7rem 1.4rem;
          border: 1px solid var(--ink);
          background: var(--ink);
          color: var(--paper);
          border-radius: 8px;
          font-weight: 500;
        }
        .composer button:disabled { opacity: 0.35; cursor: not-allowed; }

        @media (max-width: 1000px) {
          article { grid-template-columns: 1fr; gap: 0.75rem; }
          .col { padding: 1.25rem 1rem; }
          .composer { padding: 0.75rem 1rem; }
        }
      `}</style>
    </Shell>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatInner />
    </Suspense>
  );
}