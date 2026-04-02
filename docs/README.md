# docs/

Research notes, architecture decisions, and reference material.

## What belongs here

- `research/` — Notes from Phase 1 research on each data source
  - `acoustid.md` — AcoustID API outputs, rate limits, match rate on real tracks
  - `musicbrainz.md` — MusicBrainz field inventory and reliability notes
  - `discogs.md` — Discogs API coverage for electronic music
  - `mutagen.md` — File tag fields and reliability on DJ libraries
- `decisions/` — Architecture decision records (ADRs)
  - One file per significant decision, with context, options considered, and rationale
- `schema/` — Database schema design notes (written during Phase 1, before implementation)

## How to write a decision record

When you make a non-obvious architectural decision, write a short note here:
1. What the decision is
2. Why you made it (constraints, trade-offs)
3. What you considered and rejected, and why
4. What would cause you to revisit this decision

This prevents re-litigating the same decisions six months later.
