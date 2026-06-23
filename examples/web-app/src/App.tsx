import { useCallback, useRef, useState } from "react";
import { SttClient, type SttMode, type SttEvent } from "@manzke/stt-web-sdk";

type Status = "idle" | "connecting" | "ready" | "listening" | "error" | "stopped";

export function App() {
  const [url, setUrl] = useState("ws://localhost:8000/asr");
  const [token, setToken] = useState("");
  const [mode, setMode] = useState<SttMode>("dictation");
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");
  const [finalText, setFinalText] = useState("");
  const [partial, setPartial] = useState("");
  const clientRef = useRef<SttClient | null>(null);

  const onEvent = useCallback((e: SttEvent) => {
    switch (e.type) {
      case "open":
        setStatus("connecting");
        break;
      case "ready":
        setStatus("ready");
        break;
      case "partial":
        setStatus("listening");
        setPartial(e.transcript.text);
        break;
      case "final":
        setPartial("");
        setFinalText((prev) => (prev ? prev + " " : "") + e.transcript.text);
        break;
      case "error":
        setError(e.error.message);
        setStatus("error");
        break;
      case "close":
        setStatus("stopped");
        break;
    }
  }, []);

  const start = useCallback(async () => {
    setError("");
    setFinalText("");
    setPartial("");
    setStatus("connecting");
    const client = new SttClient({
      url,
      mode,
      token: token || undefined,
      // The worklet is served as a static file from public/ (see vite/public).
      workletUrl: new URL("/pcm-worklet.js", window.location.origin).toString(),
    });
    client.on(onEvent);
    clientRef.current = client;
    try {
      await client.start();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }, [url, mode, token, onEvent]);

  const stop = useCallback(async () => {
    await clientRef.current?.stop();
    clientRef.current = null;
    setStatus("stopped");
  }, []);

  const running = status === "connecting" || status === "ready" || status === "listening";

  return (
    <main style={styles.main}>
      <h1>Self-hosted STT — reference app</h1>
      <p style={{ color: "#555" }}>
        Dictation &amp; live captions over WSS using <code>@manzke/stt-web-sdk</code>.
        Audio stays on your server.
      </p>

      <section style={styles.controls}>
        <label style={styles.label}>
          Server URL
          <input style={styles.input} value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label style={styles.label}>
          Token (optional)
          <input
            style={styles.input}
            value={token}
            placeholder="bearer token for ?token="
            onChange={(e) => setToken(e.target.value)}
          />
        </label>
        <div style={styles.row}>
          <div style={styles.tabs}>
            {(["dictation", "subtitles"] as SttMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                disabled={running}
                style={{ ...styles.tab, ...(mode === m ? styles.tabActive : {}) }}
              >
                {m === "dictation" ? "Dictation" : "Live captions"}
              </button>
            ))}
          </div>
          {!running ? (
            <button style={styles.primary} onClick={start}>Start</button>
          ) : (
            <button style={styles.primary} onClick={stop}>Stop</button>
          )}
          <span style={styles.status}>{status}</span>
        </div>
      </section>

      {error && <p style={styles.error}>⚠ {error}</p>}

      <section style={styles.output} aria-live="polite">
        {finalText}
        {partial && <span style={{ color: "#888" }}>{finalText ? " " : ""}{partial}</span>}
        {!finalText && !partial && <span style={{ color: "#aaa" }}>Transcript will appear here…</span>}
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  main: { fontFamily: "system-ui, sans-serif", maxWidth: 760, margin: "2rem auto", padding: "0 1rem" },
  controls: { display: "flex", flexDirection: "column", gap: ".75rem", marginBottom: "1rem" },
  label: { display: "flex", flexDirection: "column", gap: ".25rem", fontSize: ".9rem", color: "#333" },
  input: { padding: ".5rem", fontSize: "1rem", borderRadius: 6, border: "1px solid #ccc" },
  row: { display: "flex", gap: ".5rem", alignItems: "center", flexWrap: "wrap" },
  tabs: { display: "flex", border: "1px solid #ccc", borderRadius: 6, overflow: "hidden" },
  tab: { padding: ".5rem .9rem", border: "none", background: "#f4f4f4", cursor: "pointer" },
  tabActive: { background: "#2563eb", color: "white" },
  primary: { padding: ".5rem 1.1rem", fontSize: "1rem", borderRadius: 6, border: "none", background: "#111", color: "white", cursor: "pointer" },
  status: { color: "#666", fontVariant: "small-caps" },
  error: { color: "#b00020" },
  output: { border: "1px solid #ddd", borderRadius: 8, padding: "1rem", minHeight: "8rem", whiteSpace: "pre-wrap", lineHeight: 1.5 },
};
