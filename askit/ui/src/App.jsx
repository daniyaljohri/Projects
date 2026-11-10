import { useEffect, useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const PREVIEW_ROWS = 10;
// label columns, so 2016 stays 2016 and not 2,016 (same rule as the backend)
const PLAIN_NUMBER = /(year|month|quarter|week|day|_id|_key|zip|code)$/i;

const OUTCOME_NOTES = {
  declined: "Not answered from the data",
  blocked: "Query blocked by the safety checks",
  failed: "The query failed",
};

function newSessionId() {
  return crypto.randomUUID();
}

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response;
}

function formatCell(value, column) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (PLAIN_NUMBER.test(column)) return String(value);
    const digits = Number.isInteger(value) ? 0 : Math.abs(value) >= 100 ? 2 : 3;
    return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: Number.isInteger(value) ? 0 : Math.min(digits, 2) });
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return value.endsWith("T00:00:00") ? value.slice(0, 10) : value.slice(0, 16).replace("T", " ");
  }
  return String(value);
}

function ResultTable({ columns, rows, rowCount, truncated }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? rows : rows.slice(0, PREVIEW_ROWS);
  const total = truncated ? `${rowCount.toLocaleString()}+` : rowCount.toLocaleString();

  return (
    <div className="result">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {shown.map((row, i) => (
              <tr key={i}>
                {columns.map((c) => (
                  <td key={c} className={typeof row[c] === "number" ? "num" : ""}>{formatCell(row[c], c)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rowCount > PREVIEW_ROWS && (
        <div className="table-note">
          Showing {shown.length.toLocaleString()} of {total} rows
          {rows.length > PREVIEW_ROWS && (
            <button className="link" onClick={() => setExpanded(!expanded)}>
              {expanded ? "show fewer" : `show ${rows.length.toLocaleString()}`}
            </button>
          )}
          {rowCount > rows.length && " · download Excel for all rows"}
        </div>
      )}
    </div>
  );
}

function SqlToggle({ sql, error }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button className="chip" onClick={() => setOpen(!open)}>
        {open ? "Hide SQL" : "Show SQL"}
      </button>
      {open && (
        <pre className="sql">
          {sql}
          {error && `\n\n-- ${error}`}
        </pre>
      )}
    </>
  );
}

function DownloadButton({ sessionId, answerId }) {
  const [state, setState] = useState("idle");

  async function download() {
    setState("loading");
    try {
      const response = await api("/export", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, answer_id: answerId }),
      });
      const name = response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "askit_results.xlsx";
      const url = URL.createObjectURL(await response.blob());
      const link = Object.assign(document.createElement("a"), { href: url, download: name });
      link.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 3000);
    }
  }

  return (
    <button className="chip primary" onClick={download} disabled={state === "loading"}>
      {state === "loading" ? "Preparing…" : state === "error" ? "Download failed, retry" : "Download Excel"}
    </button>
  );
}

function Message({ message, sessionId }) {
  if (message.role === "user") {
    return <div className="message user"><div className="bubble">{message.text}</div></div>;
  }

  const hasRows = message.rows?.length > 0;
  return (
    <div className="message assistant">
      <div className="avatar">A</div>
      <div className="bubble">
        {OUTCOME_NOTES[message.outcome] && <div className={`badge ${message.outcome}`}>{OUTCOME_NOTES[message.outcome]}</div>}
        <p>{message.text}</p>
        {hasRows && (
          <ResultTable columns={message.columns} rows={message.rows} rowCount={message.rowCount} truncated={message.truncated} />
        )}
        {(message.sql || hasRows) && (
          <div className="actions">
            {message.sql && <SqlToggle sql={message.sql} error={message.error} />}
            {hasRows && <DownloadButton sessionId={sessionId} answerId={message.id} />}
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [pack, setPack] = useState(null);
  const [status, setStatus] = useState("connecting");
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    api("/pack")
      .then((response) => response.json())
      .then((data) => {
        setPack(data);
        setStatus("connected");
      })
      .catch((err) => {
        setStatus("offline");
        setError(`Can't reach the Askit API at ${API_URL}. Start it with "python -m askit serve". (${err.message})`);
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 160)}px`;
  }, [input]);

  async function send(text = input.trim()) {
    if (!text || loading) return;
    setInput("");
    setError(null);
    setMessages((previous) => [...previous, { role: "user", text }]);
    setLoading(true);

    try {
      const response = await api("/chat", {
        method: "POST",
        body: JSON.stringify({ question: text, session_id: sessionId }),
      });
      const data = await response.json();
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          id: data.id,
          outcome: data.outcome,
          text: data.answer,
          sql: data.sql,
          error: data.error,
          columns: data.columns,
          rows: data.rows,
          rowCount: data.row_count,
          truncated: data.truncated,
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function clearConversation() {
    api(`/sessions/${sessionId}`, { method: "DELETE" }).catch(() => {});
    setSessionId(newSessionId());
    setMessages([]);
    setError(null);
    inputRef.current?.focus();
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">Askit</div>
        <div className="tagline">Ask your data anything</div>

        {pack?.suggested_questions?.length > 0 && <div className="section-label">Try asking</div>}
        {pack?.suggested_questions?.map((question) => (
          <button key={question} className="suggestion" onClick={() => send(question)} disabled={loading}>
            {question}
          </button>
        ))}

        <div className="spacer" />
        {messages.length > 0 && (
          <button className="clear" onClick={clearConversation}>Clear conversation</button>
        )}
      </aside>

      <main className="chat">
        <header>
          <span className="title">{pack?.display_name ?? "Askit"}</span>
          <span className={`status ${status}`}>● {status}</span>
        </header>

        <div className="messages">
          {messages.length === 0 && !loading && (
            <div className="empty">
              <div className="empty-title">Ask a question about your data</div>
              <div>Pick a suggestion on the left or type your own. Every answer shows the SQL behind it.</div>
            </div>
          )}

          {messages.map((message, i) => (
            <Message key={i} message={message} sessionId={sessionId} />
          ))}

          {loading && (
            <div className="message assistant">
              <div className="avatar">A</div>
              <div className="bubble typing"><span /><span /><span /></div>
            </div>
          )}

          {error && <div className="error">{error}</div>}
          <div ref={bottomRef} />
        </div>

        <footer>
          <div className={`composer ${loading ? "busy" : ""}`}>
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              placeholder="Ask a question about your data…"
              disabled={loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button className="send" onClick={() => send()} disabled={loading || !input.trim()} aria-label="Send">↑</button>
          </div>
          <div className="hint">Enter to send · Shift+Enter for a new line</div>
        </footer>
      </main>
    </div>
  );
}
