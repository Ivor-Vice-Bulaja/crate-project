"""
run_essentia.py -- Run Essentia analysis on an audio file and print all outputs.

Run from the project root in WSL:
    .venv/bin/python scripts/run_essentia.py "Cevi - High Line.wav"
    .venv/bin/python scripts/run_essentia.py "Cevi - High Line.wav" --no-ml
    .venv/bin/python scripts/run_essentia.py "Cevi - High Line.wav" --no-pitch
    .venv/bin/python scripts/run_essentia.py --help
"""

import argparse
import os
import sys
from pathlib import Path


def fmt_value(value, array_preview=6):
    """Format a result value for readable display."""
    if value is None:
        return "None"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, list):
        if len(value) == 0:
            return "[]"
        # Embeddings are large — just show shape
        if len(value) > 50:
            sample = [f"{v:.4f}" for v in value[:array_preview]]
            return f"[{', '.join(sample)}, ...]  ({len(value)} values)"
        # Short arrays — show all, rounded
        if all(isinstance(v, float) for v in value):
            return "[" + ", ".join(f"{v:.4f}" for v in value) + "]"
        return str(value)
    return str(value)


def print_section(title, keys, result):
    print(f"\n  {title}")
    print(f"  {'─' * len(title)}")
    for key in keys:
        value = result.get(key)
        print(f"  {key:<35} {fmt_value(value)}")


def main():
    parser = argparse.ArgumentParser(
        description="Run Essentia audio analysis on a track and print all outputs."
    )
    parser.add_argument("file", help="Path to the audio file")
    parser.add_argument("--no-ml", action="store_true", help="Skip ML models (faster)")
    parser.add_argument(
        "--no-pitch", action="store_true", help="Skip pitch analysis (slow, ~10-30s)"
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Path to model directory (default: models/ in project root)",
    )
    args = parser.parse_args()

    # Resolve the file path — handles both Windows and relative paths
    file_path = Path(args.file)
    if not file_path.is_absolute():
        # Relative path — resolve from current working directory
        file_path = Path(os.getcwd()) / file_path
    file_path = file_path.resolve()

    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    # Resolve model dir relative to this script's project root
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    model_dir = Path(args.model_dir) if args.model_dir else project_root / "models"

    from backend.config import EssentiaConfig
    from backend.importer.essentia_analysis import analyse_track

    config = EssentiaConfig(
        run_ml_models=not args.no_ml,
        run_pitch_analysis=not args.no_pitch,
        model_dir=model_dir,
    )

    print(f"\nAnalysing: {file_path.name}")
    print(f"  ML models:      {'disabled' if args.no_ml else 'enabled'}")
    print(f"  Pitch analysis: {'disabled' if args.no_pitch else 'enabled'}")
    print(f"  Model dir:      {model_dir}")
    print()

    result = analyse_track(str(file_path), config)

    if "analysis_error" in result:
        print(f"\nANALYSIS FAILED: {result['analysis_error']}")
        sys.exit(1)

    # ── Metadata ──────────────────────────────────────────────────────────────
    print_section(
        "Metadata",
        [
            "essentia_version",
            "analysis_timestamp",
        ],
        result,
    )

    # ── Rhythm ────────────────────────────────────────────────────────────────
    print_section(
        "Rhythm",
        [
            "bpm",
            "bpm_confidence",
            "bpm_estimates",
            "bpm_intervals",
            "beat_ticks",
        ],
        result,
    )

    # ── Danceability ──────────────────────────────────────────────────────────
    print_section(
        "Danceability (classical algorithm)",
        [
            "danceability",
            "danceability_dfa",
        ],
        result,
    )

    # ── Key & Tuning ──────────────────────────────────────────────────────────
    print_section(
        "Key & Tuning",
        [
            "key",
            "key_scale",
            "key_strength",
            "tuning_frequency_hz",
            "tuning_cents",
        ],
        result,
    )

    # ── Loudness ──────────────────────────────────────────────────────────────
    print_section(
        "Loudness",
        [
            "integrated_loudness",
            "loudness_range",
            "dynamic_complexity",
            "dynamic_complexity_loudness",
            "momentary_loudness",
            "short_term_loudness",
        ],
        result,
    )

    # ── Spectral ──────────────────────────────────────────────────────────────
    print_section(
        "Spectral",
        [
            "spectral_centroid_hz",
            "sub_bass_ratio",
            "high_freq_ratio",
            "mfcc_mean",
            "mfcc_var",
            "bark_bands_mean",
        ],
        result,
    )

    # ── Onsets ────────────────────────────────────────────────────────────────
    print_section(
        "Onsets",
        [
            "onset_rate",
            "onset_times",
        ],
        result,
    )

    # ── Pitch ─────────────────────────────────────────────────────────────────
    print_section(
        "Pitch (PredominantPitchMelodia)",
        [
            "pitch_frames",
            "pitch_confidence_frames",
        ],
        result,
    )

    # ── ML: Genre ─────────────────────────────────────────────────────────────
    print_section(
        "ML — Genre (Discogs-EffNet, top labels)",
        [
            "genre_top_labels",
            "genre_probabilities",
        ],
        result,
    )

    # ── ML: Mood ──────────────────────────────────────────────────────────────
    print_section(
        "ML — Mood / Valence-Arousal (DEAM)",
        [
            "arousal",
            "valence",
        ],
        result,
    )

    print_section(
        "ML — Mood classifiers (binary, 0–1)",
        [
            "mood_aggressive",
            "mood_happy",
            "mood_party",
            "mood_relaxed",
            "mood_sad",
        ],
        result,
    )

    print_section(
        "ML — Mood/Theme (MTG-Jamendo, top labels)",
        [
            "moodtheme_top_labels",
            "moodtheme_probabilities",
        ],
        result,
    )

    # ── ML: Danceability ──────────────────────────────────────────────────────
    print_section(
        "ML — Danceability (Discogs-EffNet, 0–1)",
        [
            "ml_danceability",
        ],
        result,
    )

    # ── ML: Instruments ───────────────────────────────────────────────────────
    print_section(
        "ML — Instruments (MTG-Jamendo, top labels)",
        [
            "instrument_top_labels",
            "instrument_probabilities",
        ],
        result,
    )

    # ── ML: Voice ─────────────────────────────────────────────────────────────
    print_section(
        "ML — Voice probability (0 = instrumental, 1 = vocal)",
        [
            "voice_probability",
            "voice_probability_musicnn",
        ],
        result,
    )

    # ── ML: Embeddings ────────────────────────────────────────────────────────
    print_section(
        "ML — Embeddings (512-dim vectors, preview only)",
        [
            "embedding",
            "embedding_track",
            "embedding_artist",
            "embedding_label",
            "embedding_release",
        ],
        result,
    )

    print()


if __name__ == "__main__":
    main()
