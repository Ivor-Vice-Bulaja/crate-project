# Plan: Database Schema — backend/database.py

## Overview

This plan specifies the complete SQLite schema for Crate and the step-by-step
implementation of `backend/database.py`. The schema uses a single wide `tracks`
table (Option A, decided in the research document) with source-prefixed columns
for every field returned by the five implemented importers: mutagen tags,
AcoustID + MusicBrainz, Discogs, iTunes, Cover Art Archive, and Essentia. A
separate `vec_tracks` virtual table stores 1280-dim EffNet embeddings for vector
similarity search. Schema evolution is managed via `PRAGMA user_version` migrations.
The crate management tables (`crates`, `crate_tracks`, `crate_corrections`) are
included as Migration 4. The file is the single source of truth for the database —
no schema SQL lives anywhere else.

---

## Column Inventory

Columns are grouped by logical section. All importer columns are nullable —
import failures must not prevent a row from existing.

### File Identity

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | INTEGER | NO | Primary key, AUTOINCREMENT |
| `file_path` | TEXT | NO | UNIQUE — deduplication key |
| `file_hash` | TEXT | YES | SHA-256 of file contents for change detection |
| `file_size_bytes` | INTEGER | YES | From `os.stat` |
| `file_modified_at` | TEXT | YES | ISO 8601 from `os.stat().st_mtime` |

### Audio Stream Properties (from mutagen)

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `tag_file_format` | TEXT | YES | `file_format` | "mp3", "flac", "aiff", "wav", "m4a", "ogg" |
| `tag_duration_seconds` | REAL | YES | `duration_seconds` | From `audio.info.length` |
| `tag_bitrate_bps` | INTEGER | YES | `bitrate_bps` | From `audio.info.bitrate` |
| `tag_bitrate_mode` | TEXT | YES | `bitrate_mode` | "CBR", "VBR", "ABR", "UNKNOWN"; MP3 only |
| `tag_sample_rate_hz` | INTEGER | YES | `sample_rate_hz` | From `audio.info.sample_rate` |
| `tag_channels` | INTEGER | YES | `channels` | From `audio.info.channels` |
| `tag_bits_per_sample` | INTEGER | YES | `bits_per_sample` | FLAC/WAV only; NULL for MP3 |
| `tag_encoder_info` | TEXT | YES | `encoder_info` | MP3 only |
| `tag_is_sketchy` | INTEGER | YES | `is_sketchy` | BOOLEAN (0/1); MP3 only |

### Tag Fields (from mutagen)

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `tag_title` | TEXT | YES | `tag_title` | TIT2 / TITLE / ©nam |
| `tag_artist` | TEXT | YES | `tag_artist` | TPE1 / ARTIST / ©ART |
| `tag_album_artist` | TEXT | YES | `tag_album_artist` | TPE2 / ALBUMARTIST / aART |
| `tag_album` | TEXT | YES | `tag_album` | TALB / ALBUM / ©alb |
| `tag_label` | TEXT | YES | `tag_label` | TPUB / ORGANIZATION / ©pub |
| `tag_catalogue_no` | TEXT | YES | `tag_catalogue_no` | TXXX:CATALOGNUMBER / CATALOGNUMBER |
| `tag_genre` | TEXT | YES | `tag_genre` | TCON / GENRE / ©gen |
| `tag_comment` | TEXT | YES | `tag_comment` | COMM / COMMENT / ©cmt |
| `tag_isrc` | TEXT | YES | `tag_isrc` | TSRC / ISRC / freeform ISRC |
| `tag_copyright` | TEXT | YES | `tag_copyright` | TCOP / COPYRIGHT / cprt |
| `tag_year_id3v24` | TEXT | YES | `tag_year_id3v24` | TDRC — ID3v2.4 date string |
| `tag_year_id3v23` | TEXT | YES | `tag_year_id3v23` | TYER — ID3v2.3 year string |
| `tag_date_released` | TEXT | YES | `tag_date_released` | TDRL |
| `tag_date_original` | TEXT | YES | `tag_date_original` | TDOR or TORY |
| `tag_date_vorbis` | TEXT | YES | `tag_date_vorbis` | DATE (VorbisComment) |
| `tag_date_mp4` | TEXT | YES | `tag_date_mp4` | ©day (MP4) |
| `tag_track_number` | TEXT | YES | `tag_track_number` | Stored as text (e.g. "1/12") |
| `tag_disc_number` | TEXT | YES | `tag_disc_number` | Stored as text (e.g. "1/2") |
| `tag_bpm` | TEXT | YES | `tag_bpm` | TBPM / BPM / tmpo — stored as text, may be non-numeric |
| `tag_key` | TEXT | YES | `tag_key` | TKEY / KEY / freeform KEY |
| `tag_energy` | TEXT | YES | `tag_energy` | TXXX:ENERGY / ENERGY — DJ software energy rating |
| `tag_initial_key_txxx` | TEXT | YES | `tag_initial_key_txxx` | TXXX:INITIALKEY — Rekordbox/Traktor key |
| `tag_has_embedded_art` | INTEGER | YES | `has_embedded_art` | BOOLEAN (0/1) |
| `tag_has_serato_tags` | INTEGER | YES | `has_serato_tags` | BOOLEAN (0/1) |
| `tag_has_traktor_tags` | INTEGER | YES | `has_traktor_tags` | BOOLEAN (0/1) |
| `tag_has_rekordbox_tags` | INTEGER | YES | `has_rekordbox_tags` | BOOLEAN (0/1) |
| `tag_id3_version` | TEXT | YES | `tag_id3_version` | e.g. "2.3.0"; ID3 files only |
| `tag_format_type` | TEXT | YES | `tag_format_type` | "id3", "vorbiscomment", "mp4", "none" |
| `tag_tags_present` | INTEGER | YES | `tags_present` | BOOLEAN (0/1) |
| `tag_error` | TEXT | YES | `tags_error` | Error message from mutagen; NULL on success |

### AcoustID

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `acoustid_id` | TEXT | YES | `acoustid_id` | UUID string |
| `acoustid_score` | REAL | YES | `acoustid_score` | 0.0–1.0 fingerprint confidence |
| `acoustid_match` | INTEGER | YES | `acoustid_match` | BOOLEAN (0/1) — TRUE if any fingerprint found |

### MusicBrainz

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `mb_recording_id` | TEXT | YES | `mb_recording_id` | UUID |
| `mb_release_id` | TEXT | YES | `mb_release_id` | UUID of selected release |
| `mb_artist_id` | TEXT | YES | `mb_artist_id` | UUID of first credited artist |
| `mb_release_group_id` | TEXT | YES | `mb_release_group_id` | UUID from AcoustID recording stub |
| `mb_release_group_type` | TEXT | YES | `mb_release_group_type` | "Album", "Single", "EP", etc. |
| `mb_title` | TEXT | YES | `title` | Recording title from MB |
| `mb_artist` | TEXT | YES | `artist` | Assembled from artist-credit array |
| `mb_artist_sort_name` | TEXT | YES | `artist_sort_name` | Sort-order name of first credited artist |
| `mb_year` | INTEGER | YES | `year` | First release year (integer) |
| `mb_duration_s` | REAL | YES | `mb_duration_s` | Recording length in seconds (from ms) |
| `mb_isrc` | TEXT | YES | `isrc` | First ISRC from isrc-list |
| `mb_release_title` | TEXT | YES | `mb_release_title` | Title of selected release |
| `mb_release_status` | TEXT | YES | `release_status` | "Official", "Promotion", "Bootleg" |
| `mb_release_country` | TEXT | YES | `release_country` | ISO 3166-1 code |
| `mb_label` | TEXT | YES | `label` | From release label-info lookup |
| `mb_catalogue_number` | TEXT | YES | `catalogue_number` | From release label-info lookup |
| `mb_has_front_art` | INTEGER | YES | `mb_has_front_art` | BOOLEAN — cover-art-archive.front flag |
| `mb_genres` | TEXT | YES | `genres` | JSON array of strings (always [] from MB) |
| `mb_tags` | TEXT | YES | `tags` | JSON array of tag name strings from tag-list |
| `mb_lookup_error` | TEXT | YES | `lookup_error` | Error message; NULL on success |

### Discogs

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `discogs_release_id` | INTEGER | YES | `discogs_release_id` | Discogs release integer ID |
| `discogs_master_id` | INTEGER | YES | `discogs_master_id` | Discogs master release ID; NULL if no master |
| `discogs_confidence` | TEXT | YES | `discogs_confidence` | "high", "low", "none" |
| `discogs_search_strategy` | TEXT | YES | `discogs_search_strategy` | "catno", "barcode", "label_title", "artist_title", "none" |
| `discogs_url` | TEXT | YES | `discogs_url` | Discogs release page URI |
| `discogs_title` | TEXT | YES | `discogs_title` | Release title |
| `discogs_year` | INTEGER | YES | `discogs_year` | Release year integer |
| `discogs_country` | TEXT | YES | `discogs_country` | Country string (e.g. "UK", "US") |
| `discogs_released` | TEXT | YES | `discogs_released` | Full date string "YYYY-MM-DD" |
| `discogs_released_formatted` | TEXT | YES | `discogs_released_formatted` | Discogs-formatted date string |
| `discogs_status` | TEXT | YES | `discogs_status` | "Accepted", "Draft", etc. |
| `discogs_data_quality` | TEXT | YES | `discogs_data_quality` | "Correct", "Complete and Correct", etc. |
| `discogs_notes` | TEXT | YES | `discogs_notes` | Release notes / liner notes |
| `discogs_artists_sort` | TEXT | YES | `discogs_artists_sort` | Sort name string |
| `discogs_num_for_sale` | INTEGER | YES | `discogs_num_for_sale` | Marketplace count |
| `discogs_lowest_price` | REAL | YES | `discogs_lowest_price` | Lowest marketplace price (float) |
| `discogs_label_id` | INTEGER | YES | `discogs_label_id` | Primary label integer ID |
| `discogs_label` | TEXT | YES | `discogs_label` | Primary label name |
| `discogs_catno` | TEXT | YES | `discogs_catno` | Primary catalogue number |
| `discogs_label_entity_type` | TEXT | YES | `discogs_label_entity_type` | Label entity type name |
| `discogs_artists` | TEXT | YES | `discogs_artists` | JSON array of artist name strings |
| `discogs_genres` | TEXT | YES | `discogs_genres` | JSON array of genre strings (e.g. ["Electronic"]) |
| `discogs_styles` | TEXT | YES | `discogs_styles` | JSON array of style strings (e.g. ["Techno","Industrial"]) |
| `discogs_styles_search` | TEXT | YES | — | Space-joined styles for LIKE queries; e.g. "Techno Industrial" |
| `discogs_format_names` | TEXT | YES | `discogs_format_names` | JSON array e.g. ["Vinyl"] |
| `discogs_format_descs` | TEXT | YES | `discogs_format_descs` | JSON array e.g. ['12"', "45 RPM"] |
| `discogs_producers` | TEXT | YES | `discogs_producers` | JSON array of producer name strings |
| `discogs_remixers` | TEXT | YES | `discogs_remixers` | JSON array of remixer name strings |
| `discogs_extraartists_raw` | TEXT | YES | `discogs_extraartists_raw` | JSON array of {name, role} objects |
| `discogs_labels_raw` | TEXT | YES | `discogs_labels_raw` | JSON array of all label objects |
| `discogs_tracklist` | TEXT | YES | `discogs_tracklist` | JSON array of track objects |
| `discogs_barcodes` | TEXT | YES | `discogs_barcodes` | JSON array of barcode strings |
| `discogs_matrix_numbers` | TEXT | YES | `discogs_matrix_numbers` | JSON array of matrix/runout strings |
| `discogs_have` | INTEGER | YES | `discogs_have` | Community have count |
| `discogs_want` | INTEGER | YES | `discogs_want` | Community want count |
| `discogs_rating_avg` | REAL | YES | `discogs_rating_avg` | Community average rating |
| `discogs_rating_count` | INTEGER | YES | `discogs_rating_count` | Community rating count |
| `discogs_master_year` | INTEGER | YES | `discogs_master_year` | Master release year |
| `discogs_master_most_recent_id` | INTEGER | YES | `discogs_master_most_recent_id` | Most recent release ID from master |
| `discogs_master_url` | TEXT | YES | `discogs_master_url` | Master release URL |
| `discogs_lookup_timestamp` | TEXT | YES | `discogs_lookup_timestamp` | ISO 8601 UTC timestamp of lookup |
| `discogs_error` | TEXT | YES | `discogs_error` | Error message; NULL on success |

### iTunes

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `itunes_track_id` | INTEGER | YES | `itunes_track_id` | iTunes Store track integer ID |
| `itunes_artist_id` | INTEGER | YES | `itunes_artist_id` | iTunes artist integer ID |
| `itunes_collection_id` | INTEGER | YES | `itunes_collection_id` | iTunes album integer ID |
| `itunes_confidence` | TEXT | YES | `itunes_confidence` | "high", "low", "none" |
| `itunes_track_name` | TEXT | YES | `itunes_track_name` | Track title as listed on iTunes |
| `itunes_artist_name` | TEXT | YES | `itunes_artist_name` | Artist name as listed on iTunes |
| `itunes_collection_name` | TEXT | YES | `itunes_collection_name` | Album/collection name |
| `itunes_release_date` | TEXT | YES | `itunes_release_date` | ISO 8601 e.g. "2005-01-01T00:00:00Z" |
| `itunes_track_time_ms` | INTEGER | YES | `itunes_track_time_ms` | Track duration in milliseconds |
| `itunes_disc_count` | INTEGER | YES | `itunes_disc_count` | Number of discs |
| `itunes_disc_number` | INTEGER | YES | `itunes_disc_number` | Disc number of this track |
| `itunes_track_count` | INTEGER | YES | `itunes_track_count` | Total tracks on release |
| `itunes_track_number` | INTEGER | YES | `itunes_track_number` | Track number on disc |
| `itunes_genre` | TEXT | YES | `itunes_genre` | primaryGenreName (coarse: "Dance", "Electronic") |
| `itunes_track_explicit` | TEXT | YES | `itunes_track_explicit` | "explicit", "cleaned", or "notExplicit" |
| `itunes_is_streamable` | INTEGER | YES | `itunes_is_streamable` | BOOLEAN (0/1) |
| `itunes_artwork_url` | TEXT | YES | `itunes_artwork_url` | Resized artworkUrl100 (e.g. 600×600); primary value-add |
| `itunes_track_url` | TEXT | YES | `itunes_track_url` | iTunes Store track page URL |
| `itunes_artist_url` | TEXT | YES | `itunes_artist_url` | iTunes Store artist page URL |
| `itunes_collection_url` | TEXT | YES | `itunes_collection_url` | iTunes Store album page URL |
| `itunes_collection_artist_id` | INTEGER | YES | `itunes_collection_artist_id` | Collection artist integer ID |
| `itunes_collection_artist_name` | TEXT | YES | `itunes_collection_artist_name` | Collection artist name |
| `itunes_search_strategy` | TEXT | YES | `itunes_search_strategy` | "artist_title", "id", "none" |
| `itunes_country` | TEXT | YES | `itunes_country` | Store country queried (e.g. "us") |
| `itunes_lookup_timestamp` | TEXT | YES | `itunes_lookup_timestamp` | ISO 8601 UTC timestamp of lookup |
| `itunes_error` | TEXT | YES | `itunes_error` | Error message; NULL on success |

### Cover Art Archive

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `caa_url` | TEXT | YES | `cover_art_url` | Canonical CAA request URL (not archive.org redirect) |
| `caa_source` | TEXT | YES | `cover_art_source` | "release" or "release_group" |
| `caa_lookup_timestamp` | TEXT | YES | `cover_art_lookup_timestamp` | ISO 8601 UTC timestamp of lookup |
| `caa_error` | TEXT | YES | `cover_art_error` | Error message; NULL on success |

### Essentia — Rhythm / BPM

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_bpm` | REAL | YES | `bpm` | RhythmExtractor2013 BPM float |
| `es_bpm_confidence` | REAL | YES | `bpm_confidence` | 0–5.32 confidence score |
| `es_beat_ticks` | TEXT | YES | `beat_ticks` | JSON float array — beat positions in seconds |
| `es_bpm_estimates` | TEXT | YES | `bpm_estimates` | JSON float array — BPM estimate candidates |
| `es_bpm_intervals` | TEXT | YES | `bpm_intervals` | JSON float array — intervals between beats (seconds) |

### Essentia — Key / Harmony

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_key` | TEXT | YES | `key` | KeyExtractor key string e.g. "C", "F#" |
| `es_key_scale` | TEXT | YES | `key_scale` | "major" or "minor" |
| `es_key_strength` | REAL | YES | `key_strength` | 0–1 confidence |
| `es_tuning_frequency_hz` | REAL | YES | `tuning_frequency_hz` | Concert pitch estimate in Hz |
| `es_tuning_cents` | REAL | YES | `tuning_cents` | Deviation from 440 Hz in cents |

### Essentia — Loudness / Dynamics

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_integrated_loudness` | REAL | YES | `integrated_loudness` | EBU R128 LUFS (float, negative) |
| `es_loudness_range` | REAL | YES | `loudness_range` | LU range float |
| `es_dynamic_complexity` | REAL | YES | `dynamic_complexity` | DynamicComplexity scalar |
| `es_dynamic_complexity_loudness` | REAL | YES | `dynamic_complexity_loudness` | Associated loudness scalar |

### Essentia — Spectral / Timbral

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_spectral_centroid_hz` | REAL | YES | `spectral_centroid_hz` | Mean spectral centroid in Hz (~500–5000) |
| `es_sub_bass_ratio` | REAL | YES | `sub_bass_ratio` | Mean EnergyBandRatio 20–100 Hz |
| `es_high_freq_ratio` | REAL | YES | `high_freq_ratio` | Mean EnergyBandRatio 8000–22050 Hz |
| `es_mfcc_mean` | TEXT | YES | `mfcc_mean` | JSON float array — 13 MFCC means |
| `es_mfcc_var` | TEXT | YES | `mfcc_var` | JSON float array — 13 MFCC variances |
| `es_bark_bands_mean` | TEXT | YES | `bark_bands_mean` | JSON float array — 27 Bark band means |

### Essentia — Rhythm / Onset

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_danceability` | REAL | YES | `danceability` | Danceability scalar |
| `es_danceability_dfa` | TEXT | YES | `danceability_dfa` | JSON float array — DFA coefficients |
| `es_onset_times` | TEXT | YES | `onset_times` | JSON float array — onset positions (seconds) |
| `es_onset_rate` | REAL | YES | `onset_rate` | Onsets per second |

### Essentia — Pitch (optional, slow)

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_pitch_frames` | TEXT | YES | `pitch_frames` | JSON float array — per-frame pitch in Hz (large) |
| `es_pitch_confidence_frames` | TEXT | YES | `pitch_confidence_frames` | JSON float array — per-frame confidence 0–1 |

### Essentia — ML: Genre

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_genre_probabilities` | TEXT | YES | `genre_probabilities` | JSON float array — 400 Discogs class probabilities |
| `es_genre_top_labels` | TEXT | YES | `genre_top_labels` | JSON string array — top N Discogs genre labels |
| `es_genre_top_labels_search` | TEXT | YES | — | Space-joined genre labels for LIKE queries |

### Essentia — ML: Mood

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_arousal` | REAL | YES | `arousal` | DEAM arousal score (continuous) |
| `es_valence` | REAL | YES | `valence` | DEAM valence score (continuous) |
| `es_mood_aggressive` | REAL | YES | `mood_aggressive` | Probability 0–1 |
| `es_mood_happy` | REAL | YES | `mood_happy` | Probability 0–1 |
| `es_mood_party` | REAL | YES | `mood_party` | Probability 0–1 |
| `es_mood_relaxed` | REAL | YES | `mood_relaxed` | Probability 0–1 |
| `es_mood_sad` | REAL | YES | `mood_sad` | Probability 0–1 |

### Essentia — ML: Instrument / Theme

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_instrument_probabilities` | TEXT | YES | `instrument_probabilities` | JSON float array — 40 MTG-Jamendo instrument probabilities |
| `es_instrument_top_labels` | TEXT | YES | `instrument_top_labels` | JSON string array — top N instrument labels |
| `es_moodtheme_probabilities` | TEXT | YES | `moodtheme_probabilities` | JSON float array — 56 MTG-Jamendo mood/theme probabilities |
| `es_moodtheme_top_labels` | TEXT | YES | `moodtheme_top_labels` | JSON string array — top N mood/theme labels |

### Essentia — ML: Danceability / Voice

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_ml_danceability` | REAL | YES | `ml_danceability` | ML danceability probability (EffNet, index 0 = danceable) |
| `es_voice_probability` | REAL | YES | `voice_probability` | Voice/instrumental EffNet probability (index 1 = vocal) |
| `es_voice_probability_musicnn` | REAL | YES | `voice_probability_musicnn` | Voice/instrumental MusiCNN probability |

### Essentia — Meta

| Column | Type | Nullable | Source key | Notes |
|---|---|---|---|---|
| `es_version` | TEXT | YES | `essentia_version` | Essentia library version string |
| `es_analysis_timestamp` | TEXT | YES | `analysis_timestamp` | ISO 8601 UTC time of analysis |
| `es_analysis_error` | TEXT | YES | `analysis_error` | Error message; NULL on success |

### Derived Scores (formulas TBC)

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `energy_score` | REAL | YES | Derived from Essentia features; formula not yet locked |
| `darkness_score` | REAL | YES | Derived from Essentia features; formula not yet locked |
| `groove_score` | REAL | YES | Derived from Essentia features; formula not yet locked |

### Resolved Canonical Fields

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `resolved_title` | TEXT | YES | Computed from fallback chain; see below |
| `resolved_artist` | TEXT | YES | Computed from fallback chain |
| `resolved_bpm` | REAL | YES | Computed from fallback chain |
| `resolved_key` | TEXT | YES | Combined key+scale e.g. "C major"; from fallback chain |
| `resolved_label` | TEXT | YES | Computed from fallback chain |
| `resolved_year` | INTEGER | YES | Computed from fallback chain |
| `resolved_artwork_url` | TEXT | YES | Computed from fallback chain |

### Usage

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `last_played_at` | TEXT | YES | ISO 8601 timestamp; updated by player |
| `play_count` | INTEGER | YES | Incremented by player; starts NULL |

### Import Status Timestamps

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `imported_at` | TEXT | YES | When the row was first created |
| `tags_imported_at` | TEXT | YES | NULL until tags importer has run |
| `acoustid_imported_at` | TEXT | YES | NULL until AcoustID/MB importer has run |
| `discogs_imported_at` | TEXT | YES | NULL until Discogs importer has run |
| `itunes_imported_at` | TEXT | YES | NULL until iTunes importer has run |
| `caa_imported_at` | TEXT | YES | NULL until Cover Art Archive importer has run |
| `essentia_imported_at` | TEXT | YES | NULL until Essentia analysis has run |

---

## Resolved Field Fallback Chains

### `resolved_bpm`
1. `es_bpm` — most reliable; computed from audio signal; not subject to bad tagging
2. `tag_bpm` (cast to REAL) — present on ~60% of DJ files; may be integer string
3. NULL — if neither is available

### `resolved_key`
1. `es_key || ' ' || es_key_scale` — e.g. "C major" — computed from audio signal
2. `tag_key` — may use various notations (Camelot, open key, standard); not normalised
3. `tag_initial_key_txxx` — Rekordbox/Traktor TXXX:INITIALKEY; same reliability as tag_key
4. NULL — if none available

Note: Key notation normalisation (e.g. Camelot "8A" → "Am") is pipeline logic,
not schema logic. The `resolved_key` column stores whatever the fallback chain
provides; normalisation is done before writing.

### `resolved_title`
1. `mb_title` — canonical title from MusicBrainz; most reliable when MB matches
2. `tag_title` — from file tags; reliable for well-tagged DJ libraries
3. Filename stem (no extension) — last resort; computed by pipeline from `file_path`
4. NULL is not possible — filename stem is always available

### `resolved_artist`
1. `mb_artist` — assembled from MB artist-credit array; most reliable when MB matches
2. `tag_artist` — from file tags; reliability varies (DJ library convention)
3. `discogs_artists_sort` — fallback if MB and tags both absent
4. NULL — if none available

### `resolved_label`
1. `mb_label` — from MusicBrainz release label-info; authoritative but requires MB match
2. `discogs_label` — strong for electronic music (64% match rate); fills MB gaps
3. `tag_label` — from file tags; reliability low on typical DJ library
4. NULL — if none available

### `resolved_year`
1. `mb_year` — from MusicBrainz first-release-date; most authoritative
2. `discogs_year` — release year integer from Discogs
3. `discogs_master_year` — original release year from Discogs master
4. `tag_year_id3v24` (first 4 chars, cast to INTEGER) — ID3v2.4 TDRC
5. `tag_year_id3v23` (first 4 chars, cast to INTEGER) — ID3v2.3 TYER
6. `itunes_release_date` (first 4 chars, cast to INTEGER) — day-precision date string
7. NULL — if none available

### `resolved_artwork_url`
1. `itunes_artwork_url` — best quality; resized to configured size (default 600×600); 84% match
2. `caa_url` — Cover Art Archive canonical URL; 18% match (gated on AcoustID)
3. NULL — if neither available (do not use tag embedded art as a URL column)

---

## CREATE TABLE tracks (...)

```sql
CREATE TABLE tracks (
    -- File identity
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path                       TEXT    NOT NULL UNIQUE,
    file_hash                       TEXT,
    file_size_bytes                 INTEGER,
    file_modified_at                TEXT,

    -- Audio stream properties (mutagen)
    tag_file_format                 TEXT,
    tag_duration_seconds            REAL,
    tag_bitrate_bps                 INTEGER,
    tag_bitrate_mode                TEXT,
    tag_sample_rate_hz              INTEGER,
    tag_channels                    INTEGER,
    tag_bits_per_sample             INTEGER,
    tag_encoder_info                TEXT,
    tag_is_sketchy                  INTEGER,

    -- Tag fields (mutagen)
    tag_title                       TEXT,
    tag_artist                      TEXT,
    tag_album_artist                TEXT,
    tag_album                       TEXT,
    tag_label                       TEXT,
    tag_catalogue_no                TEXT,
    tag_genre                       TEXT,
    tag_comment                     TEXT,
    tag_isrc                        TEXT,
    tag_copyright                   TEXT,
    tag_year_id3v24                 TEXT,
    tag_year_id3v23                 TEXT,
    tag_date_released               TEXT,
    tag_date_original               TEXT,
    tag_date_vorbis                 TEXT,
    tag_date_mp4                    TEXT,
    tag_track_number                TEXT,
    tag_disc_number                 TEXT,
    tag_bpm                         TEXT,
    tag_key                         TEXT,
    tag_energy                      TEXT,
    tag_initial_key_txxx            TEXT,
    tag_has_embedded_art            INTEGER,
    tag_has_serato_tags             INTEGER,
    tag_has_traktor_tags            INTEGER,
    tag_has_rekordbox_tags          INTEGER,
    tag_id3_version                 TEXT,
    tag_format_type                 TEXT,
    tag_tags_present                INTEGER,
    tag_error                       TEXT,

    -- AcoustID
    acoustid_id                     TEXT,
    acoustid_score                  REAL,
    acoustid_match                  INTEGER,

    -- MusicBrainz
    mb_recording_id                 TEXT,
    mb_release_id                   TEXT,
    mb_artist_id                    TEXT,
    mb_release_group_id             TEXT,
    mb_release_group_type           TEXT,
    mb_title                        TEXT,
    mb_artist                       TEXT,
    mb_artist_sort_name             TEXT,
    mb_year                         INTEGER,
    mb_duration_s                   REAL,
    mb_isrc                         TEXT,
    mb_release_title                TEXT,
    mb_release_status               TEXT,
    mb_release_country              TEXT,
    mb_label                        TEXT,
    mb_catalogue_number             TEXT,
    mb_has_front_art                INTEGER,
    mb_genres                       TEXT,
    mb_tags                         TEXT,
    mb_lookup_error                 TEXT,

    -- Discogs
    discogs_release_id              INTEGER,
    discogs_master_id               INTEGER,
    discogs_confidence              TEXT,
    discogs_search_strategy         TEXT,
    discogs_url                     TEXT,
    discogs_title                   TEXT,
    discogs_year                    INTEGER,
    discogs_country                 TEXT,
    discogs_released                TEXT,
    discogs_released_formatted      TEXT,
    discogs_status                  TEXT,
    discogs_data_quality            TEXT,
    discogs_notes                   TEXT,
    discogs_artists_sort            TEXT,
    discogs_num_for_sale            INTEGER,
    discogs_lowest_price            REAL,
    discogs_label_id                INTEGER,
    discogs_label                   TEXT,
    discogs_catno                   TEXT,
    discogs_label_entity_type       TEXT,
    discogs_artists                 TEXT,
    discogs_genres                  TEXT,
    discogs_styles                  TEXT,
    discogs_styles_search           TEXT,
    discogs_format_names            TEXT,
    discogs_format_descs            TEXT,
    discogs_producers               TEXT,
    discogs_remixers                TEXT,
    discogs_extraartists_raw        TEXT,
    discogs_labels_raw              TEXT,
    discogs_tracklist               TEXT,
    discogs_barcodes                TEXT,
    discogs_matrix_numbers          TEXT,
    discogs_have                    INTEGER,
    discogs_want                    INTEGER,
    discogs_rating_avg              REAL,
    discogs_rating_count            INTEGER,
    discogs_master_year             INTEGER,
    discogs_master_most_recent_id   INTEGER,
    discogs_master_url              TEXT,
    discogs_lookup_timestamp        TEXT,
    discogs_error                   TEXT,

    -- iTunes
    itunes_track_id                 INTEGER,
    itunes_artist_id                INTEGER,
    itunes_collection_id            INTEGER,
    itunes_confidence               TEXT,
    itunes_track_name               TEXT,
    itunes_artist_name              TEXT,
    itunes_collection_name          TEXT,
    itunes_release_date             TEXT,
    itunes_track_time_ms            INTEGER,
    itunes_disc_count               INTEGER,
    itunes_disc_number              INTEGER,
    itunes_track_count              INTEGER,
    itunes_track_number             INTEGER,
    itunes_genre                    TEXT,
    itunes_track_explicit           TEXT,
    itunes_is_streamable            INTEGER,
    itunes_artwork_url              TEXT,
    itunes_track_url                TEXT,
    itunes_artist_url               TEXT,
    itunes_collection_url           TEXT,
    itunes_collection_artist_id     INTEGER,
    itunes_collection_artist_name   TEXT,
    itunes_search_strategy          TEXT,
    itunes_country                  TEXT,
    itunes_lookup_timestamp         TEXT,
    itunes_error                    TEXT,

    -- Cover Art Archive
    caa_url                         TEXT,
    caa_source                      TEXT,
    caa_lookup_timestamp            TEXT,
    caa_error                       TEXT,

    -- Essentia: rhythm / BPM
    es_bpm                          REAL,
    es_bpm_confidence               REAL,
    es_beat_ticks                   TEXT,
    es_bpm_estimates                TEXT,
    es_bpm_intervals                TEXT,

    -- Essentia: key / harmony
    es_key                          TEXT,
    es_key_scale                    TEXT,
    es_key_strength                 REAL,
    es_tuning_frequency_hz          REAL,
    es_tuning_cents                 REAL,

    -- Essentia: loudness / dynamics
    es_integrated_loudness          REAL,
    es_loudness_range               REAL,
    es_dynamic_complexity           REAL,
    es_dynamic_complexity_loudness  REAL,

    -- Essentia: spectral / timbral
    es_spectral_centroid_hz         REAL,
    es_sub_bass_ratio               REAL,
    es_high_freq_ratio              REAL,
    es_mfcc_mean                    TEXT,
    es_mfcc_var                     TEXT,
    es_bark_bands_mean              TEXT,

    -- Essentia: rhythm / onset
    es_danceability                 REAL,
    es_danceability_dfa             TEXT,
    es_onset_times                  TEXT,
    es_onset_rate                   REAL,

    -- Essentia: pitch (optional, slow)
    es_pitch_frames                 TEXT,
    es_pitch_confidence_frames      TEXT,

    -- Essentia: ML genre
    es_genre_probabilities          TEXT,
    es_genre_top_labels             TEXT,
    es_genre_top_labels_search      TEXT,

    -- Essentia: ML mood
    es_arousal                      REAL,
    es_valence                      REAL,
    es_mood_aggressive              REAL,
    es_mood_happy                   REAL,
    es_mood_party                   REAL,
    es_mood_relaxed                 REAL,
    es_mood_sad                     REAL,

    -- Essentia: ML instrument / theme
    es_instrument_probabilities     TEXT,
    es_instrument_top_labels        TEXT,
    es_moodtheme_probabilities      TEXT,
    es_moodtheme_top_labels         TEXT,

    -- Essentia: ML danceability / voice
    es_ml_danceability              REAL,
    es_voice_probability            REAL,
    es_voice_probability_musicnn    REAL,

    -- Essentia: meta
    es_version                      TEXT,
    es_analysis_timestamp           TEXT,
    es_analysis_error               TEXT,

    -- Derived scores (formulas TBC)
    energy_score                    REAL,
    darkness_score                  REAL,
    groove_score                    REAL,

    -- Resolved canonical fields
    resolved_title                  TEXT,
    resolved_artist                 TEXT,
    resolved_bpm                    REAL,
    resolved_key                    TEXT,
    resolved_label                  TEXT,
    resolved_year                   INTEGER,
    resolved_artwork_url            TEXT,

    -- Usage
    last_played_at                  TEXT,
    play_count                      INTEGER,

    -- Import status timestamps
    imported_at                     TEXT,
    tags_imported_at                TEXT,
    acoustid_imported_at            TEXT,
    discogs_imported_at             TEXT,
    itunes_imported_at              TEXT,
    caa_imported_at                 TEXT,
    essentia_imported_at            TEXT
);
```

---

## CREATE VIRTUAL TABLE vec_tracks ...

```sql
CREATE VIRTUAL TABLE vec_tracks USING vec0(
    track_id  INTEGER PRIMARY KEY,
    embedding FLOAT[1280] distance_metric=cosine
);
```

- `FLOAT[1280]` — confirmed from `essentia_analysis.py` line 288: `raw = model(audio_16k)  # (batch, 1280)`
- `distance_metric=cosine` — appropriate for EffNet embeddings (direction-encoded similarity, not magnitude)
- `track_id` links to `tracks.id`; populated by `backend/importer/embeddings.py`
- If sqlite-vec is unavailable, this migration is skipped gracefully (see database.py steps)

Insert pattern for embeddings.py (reference only — not implemented here):

```python
from sqlite_vec import serialize_float32
import numpy as np

embedding = np.array(result["embedding"], dtype=np.float32)  # shape (1280,)
conn.execute(
    "INSERT OR REPLACE INTO vec_tracks(track_id, embedding) VALUES (?, ?)",
    [track_id, serialize_float32(embedding.tolist())]
)
```

---

## Index Definitions

All indexes are created in Migration 3, after the `tracks` table exists.

```sql
-- High-priority: used in Stage 1 SQL filter on every crate fill

CREATE UNIQUE INDEX idx_tracks_file_path ON tracks(file_path);

CREATE INDEX idx_tracks_file_hash ON tracks(file_hash);

CREATE INDEX idx_tracks_resolved_bpm ON tracks(resolved_bpm);

CREATE INDEX idx_tracks_resolved_key ON tracks(resolved_key);

CREATE INDEX idx_tracks_resolved_label ON tracks(resolved_label);

CREATE INDEX idx_tracks_resolved_year ON tracks(resolved_year);

-- Medium-priority: used in library browse API (/tracks filter)

CREATE INDEX idx_tracks_resolved_artist ON tracks(resolved_artist);

CREATE INDEX idx_tracks_resolved_title ON tracks(resolved_title);

CREATE INDEX idx_tracks_acoustid_id ON tracks(acoustid_id);

-- Partial indexes

-- Only index tracks where AcoustID matched — reduces index size
CREATE INDEX idx_tracks_acoustid_matched
    ON tracks(acoustid_id)
    WHERE acoustid_id IS NOT NULL;

-- Only index tracks where Essentia has run — used in energy/loudness filters
CREATE INDEX idx_tracks_essentia_ready
    ON tracks(es_bpm, es_integrated_loudness)
    WHERE es_bpm IS NOT NULL;
```

Note: `idx_tracks_acoustid_id` and `idx_tracks_acoustid_matched` both index
`acoustid_id` — the partial index is the preferred one for filtered queries.
The full index on `acoustid_id` exists for the medium-priority lookup case
(finding a track by its acoustid_id regardless of NULL). If EXPLAIN QUERY PLAN
shows the planner preferring the full index for all queries, drop the full index
and keep only the partial.

---

## Crate Tables

Specified in CLAUDE.md; stable. Created in Migration 4.

```sql
CREATE TABLE crates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE crate_tracks (
    crate_id    TEXT    REFERENCES crates(id) ON DELETE CASCADE,
    track_id    INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    added_by    TEXT    DEFAULT 'ai',
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (crate_id, track_id)
);

CREATE TABLE crate_corrections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    crate_id     TEXT    REFERENCES crates(id),
    track_id     INTEGER REFERENCES tracks(id),
    action       TEXT,
    corrected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## database.py — Implementation Steps

### Step 1: Module structure

```python
# backend/database.py
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_VEC_AVAILABLE = False  # set to True after successful extension load
```

### Step 2: Extension loading

```python
def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    """
    Attempt to load the sqlite-vec extension.
    Returns True on success, False if unavailable.
    Logs a warning but does not raise on failure.
    """
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except ImportError:
        logger.warning(
            "sqlite-vec not installed — vector search disabled. "
            "Run: uv add sqlite-vec"
        )
        return False
    except Exception as exc:
        conn.enable_load_extension(False)
        logger.warning("sqlite-vec load failed: %s — vector search disabled", exc)
        return False
```

### Step 3: Connection setup

```python
def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
```

### Step 4: Migration runner

```python
# MIGRATIONS is a list of (version: int, sql: str) tuples.
# Each sql string may contain multiple statements separated by semicolons.
# executescript() is used — it commits any pending transaction before running.

def _run_migrations(conn: sqlite3.Connection, vec_available: bool) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in _build_migrations(vec_available):
        if version > current:
            conn.executescript(sql)
            # PRAGMA user_version cannot be set inside an explicit transaction.
            # executescript() always commits first, so this is safe.
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
            logger.debug("Applied migration %d", version)
```

### Step 5: Migration definitions

```python
def _build_migrations(vec_available: bool) -> list[tuple[int, str]]:
    """
    Return the ordered list of (version, sql) migration pairs.
    Migration 2 (vec_tracks) is only included when sqlite-vec is available.
    """
    migrations = [
        (1, _MIGRATION_1_TRACKS),
        (3, _MIGRATION_3_INDEXES),
        (4, _MIGRATION_4_CRATES),
    ]
    if vec_available:
        migrations.insert(1, (2, _MIGRATION_2_VEC))
    return sorted(migrations, key=lambda x: x[0])
```

**Migration 1** — `_MIGRATION_1_TRACKS`: the full `CREATE TABLE tracks (...)` SQL
from this document. Use `CREATE TABLE IF NOT EXISTS` for safety.

**Migration 2** — `_MIGRATION_2_VEC`: the `CREATE VIRTUAL TABLE vec_tracks ...`
statement. Only applied when sqlite-vec loaded successfully. Use
`CREATE VIRTUAL TABLE IF NOT EXISTS`.

**Migration 3** — `_MIGRATION_3_INDEXES`: all `CREATE INDEX` and
`CREATE UNIQUE INDEX` statements from this document. Use
`CREATE INDEX IF NOT EXISTS` for each.

**Migration 4** — `_MIGRATION_4_CRATES`: the three crate table `CREATE TABLE`
statements from this document. Use `CREATE TABLE IF NOT EXISTS`.

Note on version numbering: versions 1, 3, 4 are always applied. Version 2 is
only applied when vec is available. A database that was initialised without
vec (version sequence: 1→3→4, final user_version=4) can later have vec added
by inserting migration 2 — but the version gap means it will never be applied
once the DB is at version 3+. The correct approach for adding vec later is a
new migration (e.g. version 5) that creates the virtual table if it does not
already exist. For now this is acceptable: vec is expected to be present in the
primary development environment (WSL2 with sqlite-vec installed).

### Step 6: `get_db()` function

```python
def get_db(db_path: str | Path = None) -> sqlite3.Connection:
    """
    Open and configure a SQLite connection, run pending migrations, and return it.

    The caller is responsible for closing the connection.
    Typically used as:
        conn = get_db()
        try:
            ...
        finally:
            conn.close()

    Or in FastAPI with a dependency that yields and closes.

    Args:
        db_path: Path to the database file. Defaults to the value in config
                 (DB_PATH environment variable). Pass ":memory:" for tests.
    """
    from backend.config import settings  # lazy import to avoid circular deps

    path = db_path or settings.db_path
    conn = sqlite3.connect(str(path))
    _configure_connection(conn)
    vec_ok = _load_sqlite_vec(conn)
    _run_migrations(conn, vec_available=vec_ok)
    return conn
```

### Step 7: Module-level constants for migration SQL

Define the four migration SQL strings as module-level constants:

```python
_MIGRATION_1_TRACKS = """
CREATE TABLE IF NOT EXISTS tracks (
    ...  -- full CREATE TABLE statement from this document
);
"""

_MIGRATION_2_VEC = """
CREATE VIRTUAL TABLE IF NOT EXISTS vec_tracks USING vec0(
    track_id  INTEGER PRIMARY KEY,
    embedding FLOAT[1280] distance_metric=cosine
);
"""

_MIGRATION_3_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_file_path ON tracks(file_path);
CREATE INDEX IF NOT EXISTS idx_tracks_file_hash ON tracks(file_hash);
...  -- all index statements
"""

_MIGRATION_4_CRATES = """
CREATE TABLE IF NOT EXISTS crates (...);
CREATE TABLE IF NOT EXISTS crate_tracks (...);
CREATE TABLE IF NOT EXISTS crate_corrections (...);
"""
```

**Important:** `executescript()` accepts multiple statements in one string,
separated by semicolons, and handles its own transaction. Do not wrap migration
SQL in `BEGIN`/`COMMIT` — `executescript()` issues an implicit `COMMIT` first.

---

## Test Plan

File: `backend/tests/test_database.py`

- **Fresh schema applies cleanly** — call `get_db(":memory:")`, assert no
  exception, assert `conn` is a `sqlite3.Connection`.

- **`PRAGMA user_version` is correct after migration** — after `get_db(":memory:")`,
  execute `PRAGMA user_version` and assert it equals the expected final version
  (4 when sqlite-vec unavailable, 4 when available — version 2 is inserted
  between 1 and 3, so final is still 4).

- **`tracks` table exists** — `SELECT name FROM sqlite_master WHERE type='table'
  AND name='tracks'` returns one row.

- **`tracks` table has expected columns** — `PRAGMA table_info(tracks)` returns
  column names matching the full column inventory. Assert against a hardcoded
  set of at least the non-nullable columns: `id`, `file_path`.

- **`crates`, `crate_tracks`, `crate_corrections` tables exist** — same
  `sqlite_master` pattern.

- **`vec_tracks` virtual table exists when sqlite-vec is installed** —
  `SELECT name FROM sqlite_master WHERE type='table' AND name='vec_tracks'`
  returns one row. Mark this test with `pytest.importorskip("sqlite_vec")`.

- **`get_db()` returns a `sqlite3.Row`-producing connection** — execute
  `SELECT 1 AS x` and assert `isinstance(row, sqlite3.Row)` and `row["x"] == 1`.

- **Re-running migrations is idempotent** — call `get_db(":memory:")` once to
  migrate, then manually call `_run_migrations(conn, vec_available=False)` a
  second time and assert no exception (all `CREATE ... IF NOT EXISTS` guards).

- **`file_path` UNIQUE constraint is enforced** — insert a row with
  `file_path='test.mp3'`, attempt to insert a second row with the same path,
  assert `sqlite3.IntegrityError` is raised.

- **Foreign key constraints are active** — insert a row into `crate_tracks`
  with a non-existent `crate_id`, assert `sqlite3.IntegrityError` is raised
  (requires `PRAGMA foreign_keys=ON` to be effective, which `_configure_connection`
  sets).

---

## Open Questions

1. **vec version pinning** — Pin `sqlite-vec` to a specific version in
   `pyproject.toml` before Phase 2 begins. The library is pre-v1 and has broken
   its API before.

2. **Variant EffNet embeddings** (`embedding_track`, `embedding_artist`,
   `embedding_label`, `embedding_release`) — each is also 1280-dim. Should all
   four be stored in separate `vec_*` virtual tables, or only the primary
   `embedding`? Storage cost: 4 × 5,120 bytes × 20,000 tracks ≈ 400 MB extra.
   Decision deferred to Phase 2 after validating that the primary embedding
   alone is sufficient for crate fill quality.

3. **Migration version gap** — If sqlite-vec is not present at first init
   (final version = 4) and is later installed, migration 2 will never be applied
   because the DB is already past version 2. A new migration (version 5) will be
   needed to create `vec_tracks` in that scenario. Document this clearly in a
   code comment in `_build_migrations`.

4. **`get_db()` in FastAPI context** — The function as designed returns a bare
   connection the caller must close. For FastAPI dependency injection, the pattern
   is `yield`-based. The FastAPI wiring belongs in `backend/main.py` or a
   `backend/deps.py` file — not in `database.py`. Implement that in Phase 3
   when FastAPI is wired up.

5. **`discogs_styles_search` and `es_genre_top_labels_search` population** —
   These denormalised search columns must be written by the import pipeline
   at the same time as the JSON columns. The pipeline should compute them as
   `' '.join(json.loads(styles_json))` before the INSERT. This is pipeline
   logic, not schema logic — noted here as a cross-cutting constraint.
