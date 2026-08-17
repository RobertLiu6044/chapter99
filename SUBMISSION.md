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

## 2. The data model, and why

`hts_code` is a 4-int tuple because prefix queries are more efficient than string comparison. Prefix queries are also more efficient combined with a B tree index. `hts_base` holds chapters 1–97 (including superior labels with synthetic codes). `rule` / `rule_edge` hold Chapter 99 provisions and the two prose relationships (`references` to base codes, `excludes` among Chapter 99 lines). Preferential columns live in `special_base` / `special_rule`.

## 3. Part 3: what you built, and why that

A FastAPI + React explorer: search the base schedule, then show parents/children and the full Chapter 99 connected component around rules that reference that line (or an ancestor). No new tables and no stored derived graphs — closure is resolved on read. Duty calculation by product/origin is left out on purpose.

## 4. What you'd do with another week

- Precompute (or cache) Chapter 99 components for hot base codes
- better graph layout
- parse notes PDF into linkable note text
- origin + program duty calculator with agent-assisted resolution. 
- polish superior-row navigation.
- more robust parsing logic for rule descriptions. Use LLM to generate parsed references and exclusions.

## 5. Assumptions

- Direct children = one HTS segment deeper; parents = truncated prefixes.
- A rule “applies” to a searched line if it `references` that code or any ancestor.
- Chapter 99 graph closure is undirected over edges whose endpoints are both
  rules (plus outbound `references` edges to base codes for display).

## 6. Where you used AI tools

Cursor agent helped scaffold the FastAPI/React app, hierarchy queries, and Chapter 99 BFS. Graph layout and edge-matching against `hts_code` composites should be spot-checked against known lines (e.g. a 9902 “provided for in” chemical and a 9903 exclusion cluster).

## 7. Where the agent succeeded and where it failed

The Cursor agent was good at performing the task incrementally rather than one-shotting all 3 parts. The agent needed clear instructions to perform well. It succeeded at quickly generating code that can run, but failed to guarantee correctness. For example, in part 2, the agent generated the parsing logic based on the data. When inspecting the parsed rule references, most of the base case "provided for in subheading ..." were missing in `rule_edge`. I inspected the parsing function `extract_references()` and found the logic to be convoluted. I asked it to change the regex expression to use capturing group to target the hts base codes rather than capturing, string splitting, and more capturing.

The agent also failed to uphold a high standard of code quality, with most of the helper functions missing in-line comments. The structure of the code is also very confusing to read. This is because of the time constraint I was under and the nature of the project being a quick prototype. In a production setting, I would manually design the function signatures, write inline comments to guide the agent where each function is called, and ask the agent to fill in each function. 