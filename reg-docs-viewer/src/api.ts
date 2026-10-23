// Mirrors QueryResponse / CitationResponse in track-b/src/regdocs_track_b/api.py.
export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  locator: string;
}

export interface QueryResponse {
  event_id: string;
  answer: string;
  citations: Citation[];
  flags: string[];
}

export async function postQuery(question: string): Promise<QueryResponse> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}
