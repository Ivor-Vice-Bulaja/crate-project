import logging

logging.basicConfig(level=logging.WARNING)

from backend.config import EssentiaConfig  # noqa: E402
from backend.importer.essentia_analysis import _TF_AVAILABLE, analyse_track  # noqa: E402

print(f"TF_AVAILABLE: {_TF_AVAILABLE}")

config = EssentiaConfig(run_ml_models=True, run_pitch_analysis=False)
result = analyse_track("/mnt/c/Users/Gamer/code/crate-project/Cevi - High Line.wav", config)

print("--- ML Results ---")
for key in [
    "genre_top_labels",
    "ml_danceability",
    "arousal",
    "valence",
    "mood_aggressive",
    "mood_happy",
    "mood_party",
    "mood_relaxed",
    "mood_sad",
    "instrument_top_labels",
    "moodtheme_top_labels",
    "voice_probability",
    "voice_probability_musicnn",
]:
    print(f"{key}: {result.get(key)}")

for key in [
    "embedding",
    "embedding_track",
    "embedding_artist",
    "embedding_label",
    "embedding_release",
]:
    val = result.get(key)
    print(f"{key} length: {len(val) if val else None}")
