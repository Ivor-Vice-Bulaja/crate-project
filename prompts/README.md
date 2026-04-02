# prompts/

Versioned prompt files for every AI call the application makes.

## Why prompts are files, not inline strings

Prompts are the specification for AI behaviour. Changing a prompt changes what the
application does — it deserves the same treatment as changing code. Storing prompts
as versioned files means:

- Changes appear in git diffs and are reviewable
- You can roll back a prompt that made results worse
- Evals in `evals/` reference specific prompt versions by filename

## Naming convention

`{purpose}_v{n}.txt` — e.g., `crate_fill_v1.txt`, `next_track_v1.txt`

Increment the version number whenever you change a prompt that is already in use.
Do not edit a prompt in place once it has been evaluated against real data.

## What belongs here

- `crate_fill_v1.txt` — System prompt for Stage 3 of the crate-fill pipeline
- `next_track_v1.txt` — System prompt for next-track suggestion (Phase 5)
