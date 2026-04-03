"""
Tests for backend/importer/essentia_analysis.py

All standard tests use:
  - run_ml_models=False   (no essentia-tensorflow needed, fast)
  - run_pitch_analysis=False  (PredominantPitchMelodia is slow ~10-30 s)

Full-pipeline tests (all algorithms + ML) are marked @pytest.mark.slow and
excluded from the default pytest run. CI runs: pytest -m "not slow"
"""

import unittest.mock

import numpy as np
import pytest

try:
    import soundfile

    _SOUNDFILE_AVAILABLE = True
except ImportError:
    _SOUNDFILE_AVAILABLE = False

try:
    import essentia  # noqa: F401

    _ESSENTIA_AVAILABLE = True
except ImportError:
    _ESSENTIA_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ESSENTIA_AVAILABLE,
    reason="essentia not installed",
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sine_wav(tmp_path):
    """4-second 440 Hz sine wave at 44100 Hz, saved as a WAV file."""
    if not _SOUNDFILE_AVAILABLE:
        pytest.skip("soundfile not installed")
    sr = 44100
    t = np.linspace(0, 4, sr * 4, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t)
    path = tmp_path / "sine.wav"
    soundfile.write(str(path), audio, sr)
    return str(path)


@pytest.fixture
def fast_config():
    """EssentiaConfig with ML and pitch analysis disabled for fast CI runs."""
    from backend.config import EssentiaConfig

    return EssentiaConfig(run_ml_models=False, run_pitch_analysis=False)


# ---------------------------------------------------------------------------
# Key inventory — every key the module must always return
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = [
    "bpm",
    "bpm_confidence",
    "beat_ticks",
    "bpm_estimates",
    "bpm_intervals",
    "danceability",
    "danceability_dfa",
    "key",
    "key_scale",
    "key_strength",
    "tuning_frequency_hz",
    "tuning_cents",
    "integrated_loudness",
    "loudness_range",
    "momentary_loudness",
    "short_term_loudness",
    "dynamic_complexity",
    "dynamic_complexity_loudness",
    "spectral_centroid_hz",
    "sub_bass_ratio",
    "high_freq_ratio",
    "mfcc_mean",
    "mfcc_var",
    "bark_bands_mean",
    "pitch_frames",
    "pitch_confidence_frames",
    "onset_times",
    "onset_rate",
    "genre_probabilities",
    "genre_top_labels",
    "embedding",
    "embedding_track",
    "embedding_artist",
    "embedding_label",
    "embedding_release",
    "arousal",
    "valence",
    "mood_aggressive",
    "mood_happy",
    "mood_party",
    "mood_relaxed",
    "mood_sad",
    "ml_danceability",
    "instrument_probabilities",
    "instrument_top_labels",
    "moodtheme_probabilities",
    "moodtheme_top_labels",
    "voice_probability",
    "voice_probability_musicnn",
    "essentia_version",
    "analysis_timestamp",
]

_ML_KEYS = [
    "genre_probabilities",
    "genre_top_labels",
    "embedding",
    "embedding_track",
    "embedding_artist",
    "embedding_label",
    "embedding_release",
    "arousal",
    "valence",
    "mood_aggressive",
    "mood_happy",
    "mood_party",
    "mood_relaxed",
    "mood_sad",
    "ml_danceability",
    "instrument_probabilities",
    "instrument_top_labels",
    "moodtheme_probabilities",
    "moodtheme_top_labels",
    "voice_probability",
    "voice_probability_musicnn",
]

# ---------------------------------------------------------------------------
# Core assertions
# ---------------------------------------------------------------------------


def test_returns_dict(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    assert isinstance(result, dict)


def test_all_expected_keys_present(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    missing = [k for k in _EXPECTED_KEYS if k not in result]
    assert missing == [], f"Missing keys: {missing}"


def test_metadata_always_set(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    assert isinstance(result["essentia_version"], str)
    assert len(result["essentia_version"]) > 0
    assert isinstance(result["analysis_timestamp"], str)
    assert len(result["analysis_timestamp"]) > 0


def test_no_analysis_error_on_success(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    assert "analysis_error" not in result


def test_numeric_ranges(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)

    if result["bpm_confidence"] is not None:
        assert (
            0 <= result["bpm_confidence"] <= 5.32
        ), f"bpm_confidence out of range: {result['bpm_confidence']}"

    if result["key_strength"] is not None:
        assert (
            0 <= result["key_strength"] <= 1
        ), f"key_strength out of range: {result['key_strength']}"

    if result["sub_bass_ratio"] is not None:
        assert (
            0 <= result["sub_bass_ratio"] <= 1
        ), f"sub_bass_ratio out of range: {result['sub_bass_ratio']}"

    if result["high_freq_ratio"] is not None:
        assert (
            0 <= result["high_freq_ratio"] <= 1
        ), f"high_freq_ratio out of range: {result['high_freq_ratio']}"

    if result["danceability"] is not None:
        assert result["danceability"] >= 0, f"danceability negative: {result['danceability']}"


def test_list_fields_are_python_lists(sine_wav, fast_config):
    """Caller serialises to JSON before writing to SQLite; we return plain lists."""
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)

    list_fields = [
        "beat_ticks",
        "bpm_estimates",
        "bpm_intervals",
        "danceability_dfa",
        "momentary_loudness",
        "short_term_loudness",
        "mfcc_mean",
        "mfcc_var",
        "bark_bands_mean",
        "onset_times",
    ]
    for field in list_fields:
        value = result[field]
        if value is not None:
            assert isinstance(value, list), f"Expected list for {field}, got {type(value)}"


def test_mfcc_dimensions(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    if result["mfcc_mean"] is not None:
        assert len(result["mfcc_mean"]) == 13
    if result["mfcc_var"] is not None:
        assert len(result["mfcc_var"]) == 13


def test_bark_bands_dimensions(sine_wav, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track(sine_wav, fast_config)
    if result["bark_bands_mean"] is not None:
        assert len(result["bark_bands_mean"]) == 27


# ---------------------------------------------------------------------------
# Failure path tests
# ---------------------------------------------------------------------------


def test_nonexistent_file(fast_config):
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track("/nonexistent/path/track.mp3", fast_config)
    assert isinstance(result, dict)
    assert "analysis_error" in result
    assert isinstance(result["analysis_error"], str)
    assert len(result["analysis_error"]) > 0

    # All audio keys must be None
    audio_keys = [k for k in _EXPECTED_KEYS if k not in {"essentia_version", "analysis_timestamp"}]
    for key in audio_keys:
        assert result[key] is None, f"Expected None for {key} on file-not-found"

    # Metadata must still be set
    assert result["essentia_version"] is not None
    assert result["analysis_timestamp"] is not None


def test_zero_byte_file(tmp_path, fast_config):
    from backend.importer.essentia_analysis import analyse_track

    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    result = analyse_track(str(empty), fast_config)

    assert isinstance(result, dict)
    assert "analysis_error" in result
    assert result["essentia_version"] is not None
    assert result["analysis_timestamp"] is not None


def test_never_raises_on_bad_input(fast_config):
    """analyse_track must never raise, even on totally invalid input."""
    from backend.importer.essentia_analysis import analyse_track

    result = analyse_track("", fast_config)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# ML import guard tests
# ---------------------------------------------------------------------------


def test_ml_keys_none_when_tf_unavailable(sine_wav, fast_config):
    """When _TF_AVAILABLE is False, all ML keys must be None without any exception."""
    import backend.importer.essentia_analysis as module
    from backend.config import EssentiaConfig

    ml_config = EssentiaConfig(run_ml_models=True, run_pitch_analysis=False)

    with unittest.mock.patch.object(module, "_TF_AVAILABLE", False):
        result = module.analyse_track(sine_wav, ml_config)

    assert isinstance(result, dict)
    for key in _ML_KEYS:
        assert result[key] is None, f"Expected None for {key} when TF unavailable"


def test_ml_keys_none_when_run_ml_models_false(sine_wav):
    """When run_ml_models=False, ML keys must be None regardless of TF availability."""
    from backend.config import EssentiaConfig
    from backend.importer.essentia_analysis import analyse_track

    config = EssentiaConfig(run_ml_models=False, run_pitch_analysis=False)
    result = analyse_track(sine_wav, config)

    for key in _ML_KEYS:
        assert result[key] is None, f"Expected None for {key} when run_ml_models=False"


def test_pitch_keys_none_when_run_pitch_analysis_false(sine_wav):
    """When run_pitch_analysis=False, pitch keys must be None."""
    from backend.config import EssentiaConfig
    from backend.importer.essentia_analysis import analyse_track

    config = EssentiaConfig(run_ml_models=False, run_pitch_analysis=False)
    result = analyse_track(sine_wav, config)

    assert result["pitch_frames"] is None
    assert result["pitch_confidence_frames"] is None


# ---------------------------------------------------------------------------
# Slow tests — full pipeline, excluded from default pytest run
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_full_pipeline_no_ml(sine_wav):
    """All standard algorithms enabled, ML disabled. Validates full standard pipeline."""
    from backend.config import EssentiaConfig
    from backend.importer.essentia_analysis import analyse_track

    config = EssentiaConfig(run_ml_models=False, run_pitch_analysis=True)
    result = analyse_track(sine_wav, config)

    assert isinstance(result, dict)
    assert "analysis_error" not in result
    assert result["pitch_frames"] is not None
    assert len(result["pitch_frames"]) > 0
