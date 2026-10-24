import type { RegEvent } from "./api";
import { retrievedChunks } from "./api";
import AnswerText from "./AnswerText";

interface Props {
  event: RegEvent;
  // The Query tab already shows the answer and flags from the live response.
  showOutcome?: boolean;
}

export default function EventDetails({ event, showOutcome = false }: Props) {
  return (
    <>
      <p>
        <strong>{event.event_type}</strong>
      </p>
      <p className="muted">Query: {event.query}</p>

      {showOutcome && (
        <>
          <h2>Answer</h2>
          <AnswerText answer={event.answer} chunks={retrievedChunks(event)} />

          <h2>Flags</h2>
          {event.flags.length === 0 ? (
            <p className="muted">None</p>
          ) : (
            <ul className="flags">
              {event.flags.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
        </>
      )}

      <h2>Steps ({event.steps.length})</h2>
      <table>
        <thead>
          <tr>
            <th>Step</th>
            <th>Model</th>
            <th>Latency (ms)</th>
            <th>Cost</th>
            <th>Confidence</th>
          </tr>
        </thead>
        <tbody>
          {event.steps.map((s, i) => (
            <tr key={`${s.step_type}-${i}`}>
              <td>{s.step_type}</td>
              <td>{s.model}</td>
              <td>{s.latency_ms ?? "-"}</td>
              <td>{s.cost ?? "-"}</td>
              <td>{s.confidence ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {event.steps.map((s, i) =>
        s.retrieved_chunks?.length ? (
          <details key={`chunks-${i}`}>
            <summary>Retrieved chunks ({s.retrieved_chunks.length})</summary>
            {s.retrieved_chunks.map((c, j) => (
              <div key={c.chunk_id} className="chunk">
                <div className="mono">
                  [{j + 1}] {c.chunk_id} - score {c.score}
                </div>
                <p>{c.text}</p>
              </div>
            ))}
          </details>
        ) : null,
      )}

      <h2>Raw event</h2>
      <pre>{JSON.stringify(event, null, 2)}</pre>
    </>
  );
}
