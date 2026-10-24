import { useEffect, useState } from "react";
import EventModal from "./EventModal";
import {
  getQueryHistory,
  type QueryHistoryItem,
  type QueryHistoryPage,
} from "./api";

export default function HistoryTab() {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<QueryHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<QueryHistoryItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getQueryHistory(page)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [page]);

  const pageCount = data
    ? Math.max(1, Math.ceil(data.total / data.page_size))
    : 1;

  return (
    <section className="result">
      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && data.items.length === 0 && (
        <p className="muted">No queries yet.</p>
      )}
      {data && data.items.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Query</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.event_id}>
                <td className="nowrap">
                  {new Date(item.recorded_at).toLocaleString()}
                </td>
                <td>
                  <button className="link" onClick={() => setSelected(item)}>
                    {item.query}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && (
        <div className="pager">
          <button onClick={() => setPage(page - 1)} disabled={page <= 1}>
            Previous
          </button>
          <span className="muted">
            Page {page} of {pageCount} ({data.total} queries)
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={page >= pageCount}
          >
            Next
          </button>
        </div>
      )}
      {selected && (
        <EventModal item={selected} onClose={() => setSelected(null)} />
      )}
    </section>
  );
}
