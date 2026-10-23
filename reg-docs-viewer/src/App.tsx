import { useState, type FormEvent } from "react";
import { postQuery, type QueryResponse } from "./api";

export default function App() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      setResponse(await postQuery(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <h1>RegDocs Viewer</h1>
      <form onSubmit={onSubmit}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the regulatory documents…"
          rows={4}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          {loading ? "Running…" : "Run query"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {response && (
        <section className="result">
          <h2>Answer</h2>
          <p className="answer">{response.answer}</p>

          <h2>Citations ({response.citations.length})</h2>
          {response.citations.length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Marker</th>
                  <th>Document</th>
                  <th>Locator</th>
                  <th>Chunk</th>
                </tr>
              </thead>
              <tbody>
                {response.citations.map((c) => (
                  <tr key={`${c.marker}-${c.chunk_id}`}>
                    <td>[{c.marker}]</td>
                    <td>{c.document_id}</td>
                    <td>{c.locator}</td>
                    <td className="mono">{c.chunk_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Flags</h2>
          {response.flags.length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="flags">
              {response.flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}

          <h2>Event</h2>
          <p className="mono">{response.event_id}</p>

          <h2>Raw response</h2>
          <pre>{JSON.stringify(response, null, 2)}</pre>
        </section>
      )}
    </main>
  );
}
