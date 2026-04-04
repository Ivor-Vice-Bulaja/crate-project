# Task: Research AcoustID and MusicBrainz as Data Sources

## Context

Read CLAUDE.md before starting. This task is Phase 1 research — no code is written here.
The goal is to produce a complete, accurate reference document that will be used to
finalise the database schema and the import pipeline in Phase 2.

Crate is a local DJ library application for techno and house DJs. Every track gets
identified on import using audio fingerprinting. We have chosen AcoustID for fingerprinting
and MusicBrainz for metadata lookup. We need to know exactly what these services return —
from first principles, based on their actual documentation and APIs — before we design
anything around them.

**Do not rely on prior knowledge about AcoustID or MusicBrainz. Research them fresh from
the source.** The authoritative sources are:
- AcoustID API documentation: https://acoustid.org/webservice
- AcoustID fingerprinting (Chromaprint): https://acoustid.org/chromaprint
- pyacoustid library: https://github.com/beetbox/pyacoustid
- MusicBrainz API documentation: https://musicbrainz.org/doc/MusicBrainz_API
- MusicBrainz data model: https://musicbrainz.org/doc/MusicBrainz_Database
- musicbrainzngs library: https://python-musicbrainzngs.readthedocs.io/

---

## What to research

### 1. AcoustID fingerprinting — what it is and how it works

Before diving into the API, establish:
- What AcoustID actually is — what the service does, who runs it, what its data covers
- What Chromaprint is and how it relates to AcoustID (they are separate things)
- The difference between the `fpcalc` command-line tool and using Chromaprint programmatically
- How pyacoustid wraps these — what it exposes vs what you have to do yourself
- Whether `fpcalc` needs to be installed separately or is bundled

### 2. The AcoustID lookup API

Go to https://acoustid.org/webservice and document the lookup endpoint exhaustively:

**Request parameters**
- What parameters the lookup endpoint accepts (all of them, including optional ones)
- Which metadata "includes" can be requested (recordings, releasegroups, releases, tracks,
  compress, usermeta, sources) — document each one
- Rate limits — exact numbers, what happens when exceeded, whether they differ for
  registered vs anonymous API keys
- API key registration — what is required, is it free, any restrictions

**Response format**
- Exact JSON structure returned — document every field with its name, type, and meaning
- What "results" contains — the score field, what range it has, what it represents
- What a "recording" object looks like — every field
- What "releases" look like within a recording — every field
- What "releasegroups" look like — every field
- Null/missing field behaviour — which fields are always present vs sometimes absent
- Multiple results — how many results can be returned, how they are ordered

**Match confidence**
- What the `score` field actually means — is it a probability, a distance, a threshold?
- Is there an official threshold above which a match should be trusted?
- What a "no match" response looks like
- What a partial match (low confidence) looks like

### 3. pyacoustid — the Python library

Document the pyacoustid library from its source and README:
- The exact functions it exposes (not just `match` — find all of them)
- What each function returns — exact return types and structure
- The `fingerprint_file` function — inputs, outputs, what it produces
- The `lookup` function — inputs, outputs
- The `match` function — inputs, outputs, what it does differently from `lookup`
- Error types raised — what exceptions exist and when they are raised
- Any known issues or edge cases documented in the library

### 4. Real-world match rates for DJ music

This is critical for Crate. DJ libraries contain:
- Commercial releases that are on streaming platforms
- White label vinyl rips
- Promos that were never commercially released
- DJ edits and bootlegs
- Old electronic music from labels with thin MusicBrainz coverage

Research what is actually known about AcoustID match rates for these cases:
- Is there any published data on AcoustID coverage for electronic music?
- What does the AcoustID/MusicBrainz community say about coverage for techno and house?
- What does a failed lookup return — empty results, or an error?
- Is there any way to distinguish "not in database" from "fingerprint didn't match"?

Document what can be confirmed from sources. Do not speculate — if data is unavailable,
say so explicitly.

### 5. MusicBrainz — what it is and what it covers

Establish:
- What MusicBrainz is — the data model at a high level (recordings, releases,
  release groups, artists, labels, works)
- The difference between a "recording" and a "release" and a "track" in MusicBrainz terms
  (these are specific, precise concepts — document them accurately)
- What data MusicBrainz has for electronic music specifically — is there known weak
  coverage for any segment (e.g. white labels, old vinyl, certain labels)?

### 6. The MusicBrainz API

Go to https://musicbrainz.org/doc/MusicBrainz_API and document the lookup endpoint
that would be used after AcoustID returns a recording ID:

**Recording lookup**
- The exact endpoint URL structure for fetching a recording by ID
- All "inc" (includes) parameters available for a recording lookup — document each one
- Exact JSON response structure — every field, type, and meaning
- Which fields are always present vs conditionally present
- How to get artist name, release title, label, catalogue number, year, genre from a
  recording lookup — which inc parameters are needed for each

**Rate limits and usage policy**
- Exact rate limit for the MusicBrainz API (requests per second)
- The User-Agent requirement — what format is required, what happens without it
- Whether there is a recommended delay between requests
- Any restrictions on commercial or automated use

**musicbrainzngs library**
- What functions it exposes for recording lookup
- The exact return structure from `get_recording_by_id` — document every field
- What "includes" are supported by the library
- How errors and not-found cases are handled
- Any known issues with the library (maintenance status, Python version support)

### 7. Field inventory and reliability

This section is the most important output of this research for Crate's database design.

**Start from what the APIs actually return — not from what we want.**

First, produce a complete inventory of every field returned by:
- The AcoustID lookup response (at every level of nesting)
- The MusicBrainz recording lookup response (with all relevant `inc` parameters)

For each field in the inventory document:
- Field name and JSON path
- Data type and value range or format
- Whether it is always present, sometimes present, or rarely present
- What it represents — be precise, not assumed
- Any known quality issues (e.g. inconsistent population, known errors for certain
  release types, weak coverage for electronic music)

Once the full inventory is complete, note which fields map to these Crate candidates
as a secondary reference — but do not let this list constrain the inventory:
```
title, artist, album, label, catalogue_number, year, genre, isrc, duration,
mb_recording_id, mb_release_id, mb_artist_id
```

If the APIs return fields not on this list that could be useful for a DJ library,
call them out explicitly. If a field on this list does not exist or is unreliable,
say so directly.

### 8. The full lookup flow in Python

Document the complete sequence of calls needed to go from an audio file to a full set
of metadata fields. Write this as a step-by-step description, not code:

1. Fingerprint the file (what call, what returns)
2. Query AcoustID (what call, what parameters, what returns)
3. Extract recording ID from the AcoustID response (where is it in the structure)
4. Query MusicBrainz with the recording ID (what call, what inc parameters)
5. Extract each field from the MusicBrainz response (exact paths)

Include: what to do when AcoustID returns no match, what to do when MusicBrainz
returns a 404, what to do when fields are missing.

### 9. Installation

Document the correct installation procedure for both libraries:
- `pyacoustid` — exact uv/pip install command
- `musicbrainzngs` — exact uv/pip install command
- `fpcalc` (the Chromaprint binary) — how to install on Linux, macOS, Windows/WSL2;
  whether pyacoustid can use it automatically or needs configuration
- A minimal Python script that verifies both are working (fingerprint a short audio
  file and print the AcoustID response)
- Any OS-level dependencies

### 10. Edge cases and failure modes

Document what is known about:
- Very short files (clips, samples) — does fingerprinting still work?
- Files with no match in AcoustID — what exactly is returned
- Multiple high-confidence matches — how to pick the right one
- Duplicate recordings in MusicBrainz — same track released on multiple labels
- The AcoustID database being wrong (misidentified tracks) — is there any error rate data?
- Network timeouts — what the libraries do by default and how to configure timeouts

---

## Output format

Write your findings as a single Markdown document saved to:

```
docs/research/acoustid.md
```

Structure it as follows:

```
# AcoustID + MusicBrainz Research

## Sources
Links to every page consulted, so findings can be verified.

## What AcoustID Is
Orientation: Chromaprint, fpcalc, the lookup service, pyacoustid.

## AcoustID API Reference
Endpoint, parameters, response structure (every field), rate limits.
Confidence scoring explained.

## pyacoustid Reference
All functions, return types, error types.

## MusicBrainz Data Model
Recordings vs releases vs tracks vs release groups — precise definitions.

## MusicBrainz API Reference
Recording lookup endpoint, all inc parameters, full response structure.
Rate limits, User-Agent requirement.

## musicbrainzngs Reference
Functions, return structure, error handling.

## Field Inventory
Complete table of every field returned by both APIs — source, JSON path,
always/sometimes/rarely present, known quality issues.
Crate candidate fields cross-referenced at the end.

## Full Lookup Flow
Step-by-step: file → fingerprint → AcoustID → MusicBrainz → fields.
Including all failure paths.

## Match Rate Reality
What is known about coverage for electronic music, white labels, promos.
Be explicit about what could not be confirmed.

## Installation
Step-by-step for Python 3.11 and uv, including fpcalc on Linux/WSL2.

## Open Questions
Anything that cannot be confirmed from documentation alone and needs
a real test on audio files in Phase 2.
```

---

## Definition of done

- [ ] `docs/research/acoustid.md` exists and is written from primary sources
- [ ] Every AcoustID API response field is documented with its name, type, and meaning
- [ ] Every MusicBrainz recording lookup field is documented with its name, type, and meaning
- [ ] The field inventory covers every field returned by both APIs, not just the Crate candidate list
- [ ] The full lookup flow documents every step including all failure paths
- [ ] Rate limits for both services are documented with exact numbers
- [ ] Match rate reality section is explicit about what is confirmed vs unknown
- [ ] pyacoustid and musicbrainzngs installation instructions are specific to uv and WSL2
- [ ] All sources are linked so findings can be verified
- [ ] Open questions are listed so they can be answered by running real tests in Phase 2
