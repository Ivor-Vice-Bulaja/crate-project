"""
test_embeddings.py — Unit tests for backend/importer/embeddings.py.

All tests are pure unit tests — no filesystem access, no model downloads.
embed_row tests monkeypatch SentenceTransformer so the real model is never
loaded during CI.
"""

import json

import pytest

from backend.importer.embeddings import (
    _dedup,
    _model_cache,
    _parse_json_list,
    build_text,
    embed_row,
)

# ---------------------------------------------------------------------------
# Helpers — row builders
# ---------------------------------------------------------------------------

MODEL = "all-MiniLM-L6-v2"


def _row(**overrides) -> dict:
    """Minimal valid row — only resolved_title is guaranteed non-NULL."""
    base: dict = {
        "resolved_title": "Test Track",
        "resolved_artist": None,
        "resolved_bpm": None,
        "resolved_key": None,
        "resolved_label": None,
        "resolved_year": None,
        "discogs_styles": None,
        "discogs_genres": None,
        "mb_genres": None,
        "itunes_genre": None,
        "es_genre_top_labels": None,
        "es_moodtheme_top_labels": None,
        "es_mood_party": None,
        "es_mood_aggressive": None,
        "es_mood_happy": None,
        "es_mood_relaxed": None,
        "es_mood_sad": None,
        "es_voice_probability": None,
        "mb_tags": None,
        "file_path": "/music/test.mp3",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _parse_json_list
# ---------------------------------------------------------------------------


class TestParseJsonList:
    def test_none_returns_empty(self):
        assert _parse_json_list(None) == []

    def test_empty_string_returns_empty(self):
        assert _parse_json_list("") == []

    def test_list_of_strings(self):
        assert _parse_json_list(json.dumps(["Deep House", "Acid"])) == ["Deep House", "Acid"]

    def test_list_of_dicts_with_name_key(self):
        # MusicBrainz tags/genres format
        data = json.dumps([{"name": "electronic", "count": 5}, {"name": "house", "count": 3}])
        assert _parse_json_list(data) == ["electronic", "house"]

    def test_mixed_list_skips_dicts_without_name(self):
        data = json.dumps(["House", {"count": 3}, {"name": "Techno"}])
        assert _parse_json_list(data) == ["House", "Techno"]

    def test_invalid_json_returns_empty(self):
        assert _parse_json_list("not json") == []

    def test_non_list_json_returns_empty(self):
        assert _parse_json_list(json.dumps({"name": "House"})) == []

    def test_empty_list(self):
        assert _parse_json_list(json.dumps([])) == []


# ---------------------------------------------------------------------------
# _dedup
# ---------------------------------------------------------------------------


class TestDedup:
    def test_removes_case_insensitive_duplicates(self):
        assert _dedup(["Electronic", "electronic", "House"]) == ["Electronic", "House"]

    def test_preserves_insertion_order(self):
        assert _dedup(["House", "Techno", "Acid"]) == ["House", "Techno", "Acid"]

    def test_empty_list(self):
        assert _dedup([]) == []

    def test_all_unique(self):
        items = ["Deep House", "Minimal Techno", "Acid"]
        assert _dedup(items) == items


# ---------------------------------------------------------------------------
# build_text — identity
# ---------------------------------------------------------------------------


class TestBuildTextIdentity:
    def test_artist_and_title_formatted(self):
        text = build_text(_row(resolved_artist="Aphex Twin", resolved_title="Windowlicker"))
        assert "Aphex Twin - Windowlicker." in text

    def test_title_only_when_no_artist(self):
        text = build_text(_row(resolved_title="Unknown Track"))
        assert "Unknown Track." in text
        assert " - " not in text

    def test_always_non_empty(self):
        # resolved_title is guaranteed non-NULL; even a minimal row produces output
        assert build_text(_row()) != ""


# ---------------------------------------------------------------------------
# build_text — BPM and key
# ---------------------------------------------------------------------------


class TestBuildTextRhythm:
    def test_bpm_and_key_together(self):
        text = build_text(_row(resolved_bpm=128.0, resolved_key="A minor"))
        assert "128 BPM" in text
        assert "A minor" in text

    def test_bpm_only(self):
        text = build_text(_row(resolved_bpm=135.0))
        assert "135 BPM" in text
        assert "Key:" not in text

    def test_key_only(self):
        text = build_text(_row(resolved_key="F# minor"))
        assert "F# minor" in text
        assert "BPM" not in text

    def test_bpm_rounded_to_integer(self):
        text = build_text(_row(resolved_bpm=132.87))
        assert "133 BPM" in text

    def test_no_bpm_no_key_omits_rhythm_line(self):
        text = build_text(_row())
        assert "BPM" not in text
        assert "Key:" not in text


# ---------------------------------------------------------------------------
# build_text — label and year
# ---------------------------------------------------------------------------


class TestBuildTextRelease:
    def test_label_and_year_together(self):
        text = build_text(_row(resolved_label="Warp Records", resolved_year=1999))
        assert "Warp Records" in text
        assert "1999" in text

    def test_label_only(self):
        text = build_text(_row(resolved_label="Ostgut Ton"))
        assert "Ostgut Ton" in text
        assert "Released:" not in text

    def test_year_only(self):
        text = build_text(_row(resolved_year=2005))
        assert "2005" in text

    def test_no_label_no_year_omits_section(self):
        text = build_text(_row())
        assert "Label:" not in text
        assert "Released" not in text


# ---------------------------------------------------------------------------
# build_text — genre and styles
# ---------------------------------------------------------------------------


class TestBuildTextGenre:
    def test_discogs_styles_present(self):
        text = build_text(_row(discogs_styles=json.dumps(["Deep House", "Acid"])))
        assert "Styles: Deep House, Acid." in text

    def test_discogs_genres_present(self):
        text = build_text(_row(discogs_genres=json.dumps(["Electronic"])))
        assert "Electronic" in text

    def test_genres_deduplicated_across_sources(self):
        text = build_text(
            _row(
                discogs_genres=json.dumps(["Electronic"]),
                mb_genres=json.dumps([{"name": "electronic"}]),
                itunes_genre="Electronic",
            )
        )
        # "Electronic" should appear only once in the genres line
        genres_section = [p for p in text.split(".") if "Genres:" in p]
        assert len(genres_section) == 1
        assert genres_section[0].count("Electronic") == 1

    def test_mb_genres_as_dict_list(self):
        # MusicBrainz returns genres as [{"name": "...", "count": ...}]
        text = build_text(_row(mb_genres=json.dumps([{"name": "House", "count": 12}])))
        assert "House" in text

    def test_itunes_genre_included(self):
        text = build_text(_row(itunes_genre="Dance"))
        assert "Dance" in text

    def test_essentia_ml_genres(self):
        text = build_text(_row(es_genre_top_labels=json.dumps(["Techno", "Industrial"])))
        assert "ML genre: Techno, Industrial." in text

    def test_no_genre_data_omits_section(self):
        text = build_text(_row())
        assert "Styles:" not in text
        assert "Genres:" not in text
        assert "ML genre:" not in text


# ---------------------------------------------------------------------------
# build_text — Essentia ML mood and voice
# ---------------------------------------------------------------------------


class TestBuildTextMood:
    def test_mood_themes_included(self):
        text = build_text(_row(es_moodtheme_top_labels=json.dumps(["dark", "energetic"])))
        assert "Mood themes: dark, energetic." in text

    def test_high_mood_scores_become_words(self):
        text = build_text(_row(es_mood_party=0.95, es_mood_aggressive=0.80))
        assert "party" in text
        assert "aggressive" in text

    def test_low_mood_scores_omitted(self):
        text = build_text(_row(es_mood_party=0.5, es_mood_relaxed=0.65))
        assert "party" not in text
        assert "relaxed" not in text

    def test_threshold_boundary_excluded(self):
        # Exactly 0.7 should NOT be included (condition is > 0.7)
        text = build_text(_row(es_mood_happy=0.7))
        assert "happy" not in text

    def test_threshold_above_included(self):
        text = build_text(_row(es_mood_happy=0.71))
        assert "happy" in text

    def test_vocal_track_flagged(self):
        text = build_text(_row(es_voice_probability=0.85))
        assert "Contains vocals." in text

    def test_instrumental_track_flagged(self):
        text = build_text(_row(es_voice_probability=0.1))
        assert "Instrumental." in text

    def test_mid_voice_probability_still_classified(self):
        # 0.6 is the threshold: > 0.6 → vocal, else → instrumental
        text = build_text(_row(es_voice_probability=0.5))
        assert "Instrumental." in text

    def test_no_essentia_omits_mood_section(self):
        text = build_text(_row())
        assert "Mood:" not in text
        assert "Instrumental" not in text
        assert "vocals" not in text


# ---------------------------------------------------------------------------
# build_text — MusicBrainz tags
# ---------------------------------------------------------------------------


class TestBuildTextMbTags:
    def test_mb_tags_as_dict_list(self):
        tags = json.dumps([{"name": "electronic", "count": 8}, {"name": "house", "count": 5}])
        text = build_text(_row(mb_tags=tags))
        assert "electronic" in text
        assert "house" in text

    def test_mb_tags_capped_at_8(self):
        tags = json.dumps([{"name": f"tag{i}", "count": 1} for i in range(12)])
        text = build_text(_row(mb_tags=tags))
        assert "tag7" in text
        assert "tag8" not in text

    def test_no_mb_tags_omits_section(self):
        text = build_text(_row())
        assert "Tags:" not in text


# ---------------------------------------------------------------------------
# build_text — full row integration
# ---------------------------------------------------------------------------


class TestBuildTextFullRow:
    def test_full_row_contains_all_sections(self):
        row = _row(
            resolved_artist="Shed",
            resolved_title="The Traveller",
            resolved_bpm=133.0,
            resolved_key="A minor",
            resolved_label="Ostgut Ton",
            resolved_year=2010,
            discogs_styles=json.dumps(["Techno", "Minimal"]),
            discogs_genres=json.dumps(["Electronic"]),
            es_genre_top_labels=json.dumps(["Techno"]),
            es_mood_party=0.85,
            es_voice_probability=0.05,
        )
        text = build_text(row)
        assert "Shed - The Traveller." in text
        assert "133 BPM" in text
        assert "A minor" in text
        assert "Ostgut Ton" in text
        assert "2010" in text
        assert "Techno" in text
        assert "Minimal" in text
        assert "party" in text
        assert "Instrumental." in text


# ---------------------------------------------------------------------------
# embed_row — monkeypatched model
# ---------------------------------------------------------------------------


class TestEmbedRow:
    @pytest.fixture(autouse=True)
    def clear_model_cache(self):
        """Reset the module-level model cache before each test."""
        _model_cache.clear()
        yield
        _model_cache.clear()

    def test_returns_list_of_floats(self, monkeypatch):
        import numpy as np

        fake_vector = np.array([0.1, 0.2, 0.3], dtype="float32")

        class FakeModel:
            def encode(self, text, normalize_embeddings=True):
                return fake_vector

        monkeypatch.setattr(
            "backend.importer.embeddings.SentenceTransformer",
            lambda name: FakeModel(),
            raising=False,
        )
        # Patch inside the module's _get_model to use our fake
        import backend.importer.embeddings as emb_mod

        monkeypatch.setattr(emb_mod, "_get_model", lambda name: FakeModel())

        result = embed_row(_row(resolved_title="Test", resolved_artist="Artist"), MODEL)
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)
        assert len(result) == 3

    def test_model_cached_across_calls(self, monkeypatch):
        load_count = {"n": 0}

        class FakeModel:
            def encode(self, text, normalize_embeddings=True):
                import numpy as np

                return np.array([0.0], dtype="float32")

        import backend.importer.embeddings as emb_mod

        original_get = emb_mod._get_model

        def counting_get(name):
            load_count["n"] += 1
            return FakeModel()

        monkeypatch.setattr(emb_mod, "_get_model", counting_get)

        embed_row(_row(), MODEL)
        embed_row(_row(resolved_title="Other"), MODEL)
        # _get_model is called once per embed_row call; caching is inside _get_model itself.
        # This test verifies embed_row delegates to _get_model (not that caching works —
        # caching is tested separately below).
        assert load_count["n"] == 2

    def test_model_cache_prevents_reload(self, monkeypatch):
        import numpy as np

        load_count = {"n": 0}

        class FakeModel:
            def encode(self, text, normalize_embeddings=True):
                return np.array([0.0], dtype="float32")

        original_cls = None

        def fake_transformer(name):
            load_count["n"] += 1
            return FakeModel()

        import backend.importer.embeddings as emb_mod

        monkeypatch.setattr(
            "sentence_transformers.SentenceTransformer", fake_transformer, raising=False
        )

        # Call _get_model directly twice with the same name
        from backend.importer.embeddings import _get_model

        _get_model(MODEL)
        _get_model(MODEL)
        # Second call should hit the cache, not call fake_transformer again
        assert load_count["n"] == 1

    def test_returns_none_on_exception(self, monkeypatch):
        import backend.importer.embeddings as emb_mod

        def raising_get(name):
            raise RuntimeError("model load failed")

        monkeypatch.setattr(emb_mod, "_get_model", raising_get)

        result = embed_row(_row(), MODEL)
        assert result is None

    def test_empty_text_returns_none(self, monkeypatch):
        import backend.importer.embeddings as emb_mod

        # Patch build_text to return empty string
        monkeypatch.setattr(emb_mod, "build_text", lambda row: "   ")

        class FakeModel:
            def encode(self, text, normalize_embeddings=True):
                import numpy as np

                return np.array([0.0], dtype="float32")

        monkeypatch.setattr(emb_mod, "_get_model", lambda name: FakeModel())

        result = embed_row(_row(resolved_title=""), MODEL)
        assert result is None
