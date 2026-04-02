# evals/

Test cases for evaluating prompt quality. One subdirectory per prompt.

## Why evals exist

A prompt is only as good as its outputs. Evals are structured test cases that let you
measure whether a change to a prompt made things better or worse. Each eval case has:

- An input (a crate description + a set of candidate tracks)
- An expected output (which track IDs should be selected)
- A scoring method (exact match, or human review)

## What belongs here

- `crate_fill/` — Eval cases for the crate-fill prompt
  - Each case is a JSON file with `input`, `expected`, and `notes` fields
  - Run with: `uv run python scripts/run_evals.py crate_fill`

Evals are not unit tests — they measure AI quality, not code correctness.
Add a new eval case every time the AI produces a notably bad result.
