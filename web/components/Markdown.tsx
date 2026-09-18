"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders the assistant's markdown.
 *
 * The agents emit markdown — headings, bold, numbered lists, and links. Showing
 * it raw meant users read "### Calendar Events" and full Google Calendar URLs,
 * which are ~400 characters and blew out the layout.
 *
 * Links open in a new tab and carry noopener: they come from email and calendar
 * content, which is attacker-controlled text, so a link should never be able to
 * reach back into the opening page via window.opener.
 */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>

      <style jsx global>{`
        .md > *:first-child { margin-top: 0; }
        .md > *:last-child { margin-bottom: 0; }

        .md h1, .md h2, .md h3, .md h4 {
          font-family: var(--sans);
          font-weight: 600;
          line-height: 1.3;
          margin: 1.5em 0 0.5em;
        }
        .md h1 { font-size: 1.15em; }
        .md h2 { font-size: 1.08em; }
        .md h3, .md h4 { font-size: 1em; }

        .md p { margin: 0 0 0.9em; }

        .md ul, .md ol { margin: 0 0 0.9em; padding-left: 1.4em; }
        .md li { margin-bottom: 0.35em; }
        .md li > ul, .md li > ol { margin-top: 0.35em; }

        .md a {
          color: var(--agent);
          text-decoration: underline;
          text-underline-offset: 2px;
          /* Long URLs as link text must be allowed to break, or one calendar
             link stretches the whole column. */
          overflow-wrap: anywhere;
        }

        .md code {
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 0.88em;
          background: var(--sunk);
          padding: 0.12em 0.35em;
          border-radius: 4px;
        }
        .md pre {
          background: var(--sunk);
          padding: 0.9em 1em;
          border-radius: 8px;
          overflow-x: auto;
          margin: 0 0 0.9em;
        }
        .md pre code { background: none; padding: 0; }

        .md blockquote {
          margin: 0 0 0.9em;
          padding-left: 1em;
          border-left: 2px solid var(--rule);
          color: var(--ink-soft);
        }

        .md table {
          width: 100%;
          border-collapse: collapse;
          margin: 0 0 0.9em;
          font-size: 0.94em;
        }
        .md th, .md td {
          text-align: left;
          padding: 0.45em 0.7em;
          border-bottom: 1px solid var(--rule);
        }
        .md th { font-weight: 600; }

        .md hr { border: none; border-top: 1px solid var(--rule); margin: 1.4em 0; }
        .md strong { font-weight: 600; }
      `}</style>
    </div>
  );
}
