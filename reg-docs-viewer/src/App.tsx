import { useState } from "react";
import HistoryTab from "./HistoryTab";
import QueryTab from "./QueryTab";

type Tab = "query" | "history";

export default function App() {
  const [tab, setTab] = useState<Tab>("query");

  return (
    <main>
      <h1>RegDocs Viewer</h1>
      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "query"}
          className={tab === "query" ? "tab active" : "tab"}
          onClick={() => setTab("query")}
        >
          Query
        </button>
        <button
          role="tab"
          aria-selected={tab === "history"}
          className={tab === "history" ? "tab active" : "tab"}
          onClick={() => setTab("history")}
        >
          History
        </button>
      </div>

      {/* Hidden rather than unmounted so an in-flight query and its result survive a tab switch. */}
      <div hidden={tab !== "query"}>
        <QueryTab />
      </div>
      {tab === "history" && <HistoryTab />}
    </main>
  );
}
