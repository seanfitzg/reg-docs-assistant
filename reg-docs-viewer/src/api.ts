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

export interface RetrievedChunk {
  chunk_id: string;
  document_id: string;
  text: string;
  score: number;
}

export interface Step {
  step_type: string;
  model: string;
  cost?: number;
  latency_ms?: number;
  retrieved_chunks?: RetrievedChunk[];
  confidence?: number;
}

export interface RegEvent {
  id: string;
  event_type: string;
  query: string;
  answer: string;
  flags: string[];
  steps: Step[];
  [key: string]: unknown;
}

// Mirrors QueryHistoryResponse in track-b/src/regdocs_track_b/api.py.
export interface QueryHistoryItem {
  event_id: string;
  recorded_at: string;
  query: string;
}

export interface QueryHistoryPage {
  items: QueryHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export async function getQueryHistory(page: number): Promise<QueryHistoryPage> {
  const res = await fetch(`/api/queries?page=${page}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function getEvent(eventId: string): Promise<RegEvent> {
  const res = await fetch(`/api/events/${encodeURIComponent(eventId)}`);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

// Citation marker [n] is the n-th retrieved Chunk in rank order, so the
// retrieve step's list is the marker lookup table.
export function retrievedChunks(event: RegEvent | null): RetrievedChunk[] {
  if (!event) return [];
  for (const step of event.steps) {
    if (step.step_type === "retrieve") return step.retrieved_chunks ?? [];
  }
  return [];
}
