import { FormEvent, useEffect, useState, useTransition } from "react";
import {
  displayHts,
  fetchHtsDetail,
  formatRate,
  searchHts,
  type HtsDetail,
  type HtsRow,
} from "./api";
import { HierarchyPanel } from "./HierarchyPanel";
import { Chapter99Graph } from "./Chapter99Graph";

export default function App() {
  const [query, setQuery] = useState("0101.21");
  const [results, setResults] = useState<HtsRow[]>([]);
  const [detail, setDetail] = useState<HtsDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [loadingDetail, setLoadingDetail] = useState(false);

  async function runSearch(q: string) {
    setError(null);
    try {
      const data = await searchHts(q);
      startTransition(() => setResults(data.results));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
      setResults([]);
    }
  }

  async function openHts(hts: string) {
    setLoadingDetail(true);
    setError(null);
    try {
      const data = await fetchHtsDetail(hts);
      setDetail(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load HTS detail");
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) void runSearch(query.trim());
  }

  useEffect(() => {
    void runSearch("0101.21");
  }, []);

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">Chapter 99 Explorer</p>
        <h1>Find a base HTS line, then see what Chapter 99 does to it.</h1>
        <p className="lede">
          Search chapters 1–97. Open a row to walk its schedule parents and
          children, and to expand every Chapter 99 rule that references it —
          including the full exclusion graph around those rules.
        </p>
        <form className="search" onSubmit={onSubmit}>
          <label htmlFor="q" className="sr-only">
            Search HTS or description
          </label>
          <input
            id="q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="HTS code or description — e.g. 0101.21 or coffee"
            autoComplete="off"
          />
          <button type="submit" disabled={pending}>
            Search
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </header>

      <main className="layout">
        <section className="panel results">
          <h2>Base schedule</h2>
          <ul>
            {results.map((r) => (
              <li key={r.hts}>
                <button
                  type="button"
                  className={
                    detail?.selected.hts === r.hts ? "result active" : "result"
                  }
                  onClick={() => void openHts(r.hts)}
                >
                  <span className="hts">
                    {displayHts(r)}
                    {r.superior ? <em className="tag">grouping</em> : null}
                  </span>
                  <span className="desc">{r.description || "—"}</span>
                  <span className="rate">
                    {formatRate(r.mfn_rate, r.mfn_rate_unit)}
                  </span>
                </button>
              </li>
            ))}
            {!results.length && (
              <li className="empty">No rows match. Try a shorter HTS prefix.</li>
            )}
          </ul>
        </section>

        <section className="panel detail">
          {loadingDetail && <p className="muted">Loading graph…</p>}
          {!loadingDetail && !detail && (
            <p className="muted">
              Select a search result to see hierarchy and Chapter 99 links.
            </p>
          )}
          {detail && (
            <>
              <div className="selected">
                <h2>{displayHts(detail.selected)}</h2>
                <p>{detail.selected.description}</p>
                <p className="meta">
                  MFN {formatRate(detail.selected.mfn_rate, detail.selected.mfn_rate_unit)}
                  {detail.chapter99.focus.length
                    ? ` · ${detail.chapter99.focus.length} Chapter 99 rule(s) reference this line (or an ancestor)`
                    : " · no Chapter 99 references found"}
                </p>
              </div>
              <HierarchyPanel
                parents={detail.parents}
                selected={detail.selected}
                childRows={detail.children}
                onSelect={(hts) => void openHts(hts)}
              />
              <Chapter99Graph
                focus={detail.chapter99.focus}
                rules={detail.chapter99.rules}
                edges={detail.chapter99.edges}
                baseHts={detail.selected.hts}
              />
            </>
          )}
        </section>
      </main>
    </div>
  );
}
