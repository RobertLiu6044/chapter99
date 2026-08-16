# Part 3 — Chapter 99 Explorer

FastAPI + React app over the parsed Postgres data. It does **not** change
tables or store derived graphs — hierarchy and Chapter 99 closure are resolved
on each request from `hts_base`, `rule`, and `rule_edge`.

## What it does

1. Search chapters 1–97 (`hts_base`) by HTS prefix or description.
2. Open a row to see:
   - **Parents / children** in the base schedule (HTS code prefixes).
   - **Chapter 99 graph**: every rule that `references` this line or an
     ancestor, then the full connected component via `references` /
     `excludes` edges among Chapter 99 rules.

Tariff calculator (product + origin → duty) is intentionally not built yet.

## Run (host)

Postgres must be up and Part 2 data loaded (`./setup.sh` then parse).

```bash
# terminal 1 — API
cd app/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgres://postgres:postgres@localhost:5432/chp99
uvicorn main:app --reload --port 8000

# terminal 2 — UI
cd app/web
npm install
npm run dev
# → http://localhost:3000  (Vite proxies /api → :8000)
```

## Run (Docker)

```bash
docker compose --profile app up -d
# UI  http://localhost:3000
# API http://localhost:8000/docs
```

`./dev.sh` also starts the app profile (API + web) with the rest of the stack.
