# Submission

## 1. How to run it

From a fresh clone:

```bash
./dev.sh                 # Postgres, Hatchet, worker, API (:8000), UI (:3000)
./setup.sh               # apply db/schema.sql
cd workflows && uv sync && uv run python -m scrape_run   # Part 1 — land raw files in data/
cd workflows && uv run python -m parse_run               # Part 2 — fill Postgres
# open http://localhost:3000 for Part 3
```

Host-only app (DB already up):

```bash
cd app/api && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=postgres://postgres:postgres@localhost:5432/chp99 uvicorn main:app --reload --port 8000

cd app/web && npm install && npm run dev   # http://localhost:3000
```

## 2. The data model, and why

`hts_code` is a 4-int tuple so prefix queries match HTS hierarchy. `hts_base`
holds chapters 1–97 (including superior labels with synthetic codes). `rule` /
`rule_edge` hold Chapter 99 provisions and the two prose relationships
(`references` to base codes, `excludes` among Chapter 99 lines). Preferential
columns live in `special_base` / `special_rule`.

## 3. Part 3: what you built, and why that

A FastAPI + React explorer: search the base schedule, then show parents/children
and the full Chapter 99 connected component around rules that reference that
line (or an ancestor). No new tables and no stored derived graphs — closure is
resolved on read. Duty calculation by product/origin is left out on purpose.

## 4. What you'd do with another week

Precompute (or cache) Chapter 99 components for hot base codes; better graph
layout; parse notes PDF into linkable note text; origin + program duty
calculator; polish superior-row navigation.

## 5. Assumptions

- Direct children = one HTS segment deeper; parents = truncated prefixes.
- A rule “applies” to a searched line if it `references` that code or any ancestor.
- Chapter 99 graph closure is undirected over edges whose endpoints are both
  rules (plus outbound `references` edges to base codes for display).

## 6. Where you used AI tools

Cursor agent helped scaffold the FastAPI/React app, hierarchy queries, and
Chapter 99 BFS. Graph layout and edge-matching against `hts_code` composites
should be spot-checked against known lines (e.g. a 9902 “provided for in”
chemical and a 9903 exclusion cluster).
