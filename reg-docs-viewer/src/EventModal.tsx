import { useEffect, useState } from "react";
import { getEvent, type QueryHistoryItem, type RegEvent } from "./api";
import EventDetails from "./EventDetails";

interface Props {
  item: QueryHistoryItem;
  onClose: () => void;
}

export default function EventModal({ item, onClose }: Props) {
  const [event, setEvent] = useState<RegEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEvent(item.event_id)
      .then((result) => {
        if (!cancelled) setEvent(result);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [item.event_id]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Query details"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="muted">
            {new Date(item.recorded_at).toLocaleString()}
          </span>
          <button onClick={onClose}>Close</button>
        </div>
        <p className="mono">{item.event_id}</p>
        {error && <p className="error">{error}</p>}
        {!event && !error && <p className="muted">Loading…</p>}
        {event && <EventDetails event={event} showOutcome />}
      </div>
    </div>
  );
}
