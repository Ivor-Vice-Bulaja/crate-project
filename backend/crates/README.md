# backend/crates/

The AI crate-fill pipeline. Takes a crate description and returns matching tracks.

## What belongs here

- `fill.py` — Three-stage funnel: SQL hard filter → vector similarity → Claude ranking.
- `prompts.py` — Loads versioned prompt files from `prompts/`. No inline prompt strings here.
- `learn.py` — Logs manual corrections and feeds them back into description refinement.

## Three-stage funnel (at 20,000 tracks)

```
Stage 1 — SQL hard filter          20,000 → ~400 candidates    <10ms
Stage 2 — Vector similarity           400 → 80–100 candidates  <100ms
Stage 3 — Claude final ranking     80–100 → 8–15 final tracks  ~2s
```

The SQL result without Claude is still usable — AI is never load-bearing alone.
