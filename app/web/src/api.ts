export type HtsRow = {
  hts: string;
  code: number[];
  superior: boolean;
  description: string;
  mfn_rate: number | null;
  mfn_rate_unit: string | null;
};

export type RuleRow = {
  hts: string;
  code: number[];
  subchapter: string;
  description: string;
  rate_kind: string | null;
  rate_value: number | null;
  rate_unit: string | null;
  note_ref: string | null;
};

export type GraphEdge = {
  source: string;
  target: string;
  edge_type: "references" | "excludes" | string;
};

export type HtsDetail = {
  selected: HtsRow;
  parents: HtsRow[];
  children: HtsRow[];
  chapter99: {
    focus: string[];
    rules: RuleRow[];
    edges: GraphEdge[];
  };
};

const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function searchHts(q: string, limit = 25) {
  return getJson<{ query: string; results: HtsRow[] }>(
    `/api/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  );
}

export function fetchHtsDetail(hts: string) {
  return getJson<HtsDetail>(`/api/hts/${encodeURIComponent(hts)}`);
}

/** Superior rows carry a synthetic key; showing it would look like a real code. */
export function displayHts(row: { hts: string; code: number[] }): string {
  if (row.code[0] === 0 || row.hts.startsWith("sup:")) return "(grouping row)";
  return row.hts;
}

export function formatRate(rate: number | null, unit: string | null): string {
  if (unit === "free" || (rate === 0 && unit === "free")) return "Free";
  if (rate == null && !unit) return "—";
  if (unit === "percent" && rate != null) return `${rate}%`;
  if (rate != null && unit) return `${rate} ${unit}`;
  if (rate != null) return String(rate);
  return unit ?? "—";
}
