"""
embeddings.py — sentence-transformers text embedding for Crate.

Builds a natural-language description of each track from all populated
importer attributes (resolved fields, Discogs styles, Essentia ML labels,
mood scores, etc.) and encodes it with sentence-transformers.

Written to vec_tracks_text (384-dim, cosine) for every imported track.
The Essentia audio embedding (1280-dim) in vec_tracks is the primary
similarity signal when available; vec_tracks_text is the fallback and
is always populated regardless of WSL2 availability.

Public API:
    build_text(row: dict) -> str
    embed_row(row: dict, model_name: str) -> list[float] | None
"""

import json
import logging

logger = logging.getLogger(__name__)

# Module-level model cache — sentence-transformers takes a few seconds to load.
# Loaded once on first call, reused for the entire import session.
_model_cache: dict = {}


def _get_model(model_name: str):
    if model_name not in _model_cache:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model: %s", model_name)
        _model_cache[model_name] = SentenceTransformer(model_name)
        logger.info("Model loaded.")
    return _model_cache[model_name]


def _parse_json_list(value) -> list[str]:
    """
    Parse a JSON-encoded list from a DB column into a flat list of strings.

    Handles:
    - None / empty string → []
    - JSON list of strings → returned as-is
    - JSON list of dicts with a "name" key (MusicBrainz tags/genres format)
    """
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    result = []
    for item in parsed:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict) and "name" in item:
            result.append(str(item["name"]))
    return result


def _dedup(items: list[str]) -> list[str]:
    """Remove duplicates (case-insensitive) while preserving insertion order."""
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def build_text(row: dict) -> str:
    """
    Build a natural-language description of a track from all populated
    attributes in its database row.

    Source priority mirrors the resolved_* fallback chains: Essentia and
    Discogs fields carry the most semantic weight; iTunes and MusicBrainz
    tags supplement when present. Fields that are NULL or absent are skipped.

    Returns a non-empty string always — resolved_title is guaranteed
    non-NULL by the pipeline (falls back to the filename stem).
    """
    parts: list[str] = []

    # ------------------------------------------------------------------
    # Identity: artist – title
    # ------------------------------------------------------------------
    artist = row.get("resolved_artist") or ""
    title = row.get("resolved_title") or ""
    if artist and title:
        parts.append(f"{artist} - {title}.")
    elif title:
        parts.append(f"{title}.")

    # ------------------------------------------------------------------
    # Rhythm and harmony: BPM and musical key
    # ------------------------------------------------------------------
    bpm = row.get("resolved_bpm")
    key = row.get("resolved_key")
    if bpm is not None and key:
        parts.append(f"Track at {float(bpm):.0f} BPM in {key}.")
    elif bpm is not None:
        parts.append(f"Track at {float(bpm):.0f} BPM.")
    elif key:
        parts.append(f"Key: {key}.")

    # ------------------------------------------------------------------
    # Release context: label and year
    # ------------------------------------------------------------------
    label = row.get("resolved_label")
    year = row.get("resolved_year")
    if label and year:
        parts.append(f"Released on {label} in {year}.")
    elif label:
        parts.append(f"Label: {label}.")
    elif year:
        parts.append(f"Released: {year}.")

    # ------------------------------------------------------------------
    # Genre: Discogs styles are the richest signal for DJ libraries
    # (e.g. "Deep House", "Minimal Techno", "Acid") compared to the
    # coarse iTunes/MB genre labels ("Electronic", "Dance").
    # ------------------------------------------------------------------
    discogs_styles = _parse_json_list(row.get("discogs_styles"))
    if discogs_styles:
        parts.append(f"Styles: {', '.join(discogs_styles)}.")

    # Broad genre labels from multiple sources, deduplicated
    genres: list[str] = []
    for col in ("discogs_genres", "mb_genres"):
        genres.extend(_parse_json_list(row.get(col)))
    itunes_genre = row.get("itunes_genre")
    if itunes_genre:
        genres.append(str(itunes_genre))
    genres = _dedup(genres)
    if genres:
        parts.append(f"Genres: {', '.join(genres)}.")

    # ------------------------------------------------------------------
    # Essentia ML outputs (present only when analysed via WSL2)
    # ------------------------------------------------------------------
    es_genres = _parse_json_list(row.get("es_genre_top_labels"))
    if es_genres:
        parts.append(f"ML genre: {', '.join(es_genres)}.")

    es_mood_themes = _parse_json_list(row.get("es_moodtheme_top_labels"))
    if es_mood_themes:
        parts.append(f"Mood themes: {', '.join(es_mood_themes)}.")

    # Named mood words for scores above 0.7
    mood_words: list[str] = []
    for col, word in [
        ("es_mood_party", "party"),
        ("es_mood_aggressive", "aggressive"),
        ("es_mood_happy", "happy"),
        ("es_mood_relaxed", "relaxed"),
        ("es_mood_sad", "sad"),
    ]:
        val = row.get(col)
        if val is not None and float(val) > 0.7:
            mood_words.append(word)
    if mood_words:
        parts.append(f"Mood: {', '.join(mood_words)}.")

    # Vocal / instrumental classification
    voice_prob = row.get("es_voice_probability")
    if voice_prob is not None:
        if float(voice_prob) > 0.6:
            parts.append("Contains vocals.")
        else:
            parts.append("Instrumental.")

    # ------------------------------------------------------------------
    # MusicBrainz community tags (sparse for electronic, useful when present)
    # Cap at 8 to avoid diluting the embedding with noisy long-tail tags.
    # ------------------------------------------------------------------
    mb_tags = _parse_json_list(row.get("mb_tags"))
    if mb_tags:
        parts.append(f"Tags: {', '.join(mb_tags[:8])}.")

    return " ".join(parts)


def embed_row(row: dict, model_name: str) -> list[float] | None:
    """
    Build the text description for a track row and encode it.

    Args:
        row: The dict written to / read from the tracks table.
        model_name: sentence-transformers model identifier
                    (e.g. "all-MiniLM-L6-v2").

    Returns:
        A list of floats (the embedding vector), or None on failure.
        Never raises.
    """
    try:
        model = _get_model(model_name)
        text = build_text(row)
        if not text.strip():
            logger.warning("build_text returned empty string for %s — skipping", row.get("file_path"))
            return None
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as exc:
        logger.error("Text embedding failed: %s", exc)
        return None
