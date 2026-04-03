"""
essentia_analysis.py — Raw audio feature extraction using Essentia.

Takes a file path and returns a flat dict of audio features. Runs every
standard algorithm and (when available) the TensorFlow ML models. Stores
each raw output directly — no derived scores, no combinations beyond the
mean/variance aggregation needed to reduce frame-level vectors to a single
track-level descriptor.

Never raises. On any failure it returns a dict (possibly with some keys set
to None) so the pipeline can always write a partial result.

Usage:
    from backend.importer.essentia_analysis import analyse_track
    from backend.config import EssentiaConfig

    result = analyse_track("/path/to/track.mp3", EssentiaConfig())
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.config import EssentiaConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TensorFlow availability guard — checked once at module load.
# All ML keys are silently set to None when _TF_AVAILABLE is False.
# This is expected in CI and lightweight environments, not an error.
# ---------------------------------------------------------------------------
try:
    import essentia.standard as _es_check

    _TF_AVAILABLE = hasattr(_es_check, "TensorflowPredictEffnetDiscogs")
    del _es_check
except ImportError:
    _TF_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public keys — every key this module may write.
# Used to build the skeleton dict for total-failure returns.
# ---------------------------------------------------------------------------
_ALL_KEYS = [
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
]

_META_KEYS = ["essentia_version", "analysis_timestamp"]


def _null_result() -> dict:
    """Return a skeleton dict with every audio key set to None."""
    result = {k: None for k in _ALL_KEYS}
    result.update(_meta_fields())
    return result


def _meta_fields() -> dict:
    import essentia

    return {
        "essentia_version": essentia.__version__,
        "analysis_timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Frame-level processing
# ---------------------------------------------------------------------------

_FRAME_SIZE = 2048
_HOP_SIZE = 1024
_WINDOW_TYPE = "hann"


def _run_frame_loop(audio_44k) -> dict:
    """
    Single framing pass over audio_44k.

    Returns a dict with aggregated results for:
        spectral_centroid_hz, sub_bass_ratio, high_freq_ratio,
        mfcc_mean, mfcc_var, bark_bands_mean,
        all_peak_freqs, all_peak_mags  (for TuningFrequency)

    On any per-frame error the frame is skipped. If all frames fail,
    all keys are returned as None.
    """
    import essentia.standard as es

    frame_gen = es.FrameGenerator(audio_44k, frameSize=_FRAME_SIZE, hopSize=_HOP_SIZE)
    window = es.Windowing(type=_WINDOW_TYPE)
    spectrum_alg = es.Spectrum()
    mfcc_alg = es.MFCC(numberCoefficients=13, numberBands=40)
    bark_alg = es.BarkBands(numberBands=27)
    centroid_alg = es.SpectralCentroidTime()
    ebr_sub = es.EnergyBandRatio(startFrequency=20, stopFrequency=100)
    ebr_high = es.EnergyBandRatio(startFrequency=8000, stopFrequency=22050)
    peaks_alg = es.SpectralPeaks()

    mfcc_frames = []
    bark_frames = []
    centroid_frames = []
    sub_bass_frames = []
    high_freq_frames = []
    all_peak_freqs = []
    all_peak_mags = []

    failed_frames = 0
    total_frames = 0

    for frame in frame_gen:
        total_frames += 1
        try:
            windowed = window(frame)
            spec = spectrum_alg(windowed)

            mfcc_bands, mfcc_coeffs = mfcc_alg(spec)
            mfcc_frames.append(mfcc_coeffs)

            bark_bands = bark_alg(spec)
            bark_frames.append(bark_bands)

            centroid = centroid_alg(windowed)
            centroid_frames.append(centroid)

            sub_ratio = ebr_sub(spec)
            sub_bass_frames.append(sub_ratio)

            high_ratio = ebr_high(spec)
            high_freq_frames.append(high_ratio)

            peak_freqs, peak_mags = peaks_alg(spec)
            all_peak_freqs.extend(peak_freqs.tolist())
            all_peak_mags.extend(peak_mags.tolist())

        except Exception as exc:
            failed_frames += 1
            logger.debug("Frame %d failed: %s", total_frames, exc)

    if total_frames > 0 and failed_frames == total_frames:
        logger.warning("All %d frames failed in frame loop", total_frames)
        return {
            "spectral_centroid_hz": None,
            "sub_bass_ratio": None,
            "high_freq_ratio": None,
            "mfcc_mean": None,
            "mfcc_var": None,
            "bark_bands_mean": None,
            "all_peak_freqs": [],
            "all_peak_mags": [],
        }

    result = {}

    if mfcc_frames:
        arr = np.array(mfcc_frames)
        result["mfcc_mean"] = np.mean(arr, axis=0).tolist()
        result["mfcc_var"] = np.var(arr, axis=0).tolist()
    else:
        result["mfcc_mean"] = None
        result["mfcc_var"] = None

    result["bark_bands_mean"] = (
        np.mean(np.array(bark_frames), axis=0).tolist() if bark_frames else None
    )
    result["spectral_centroid_hz"] = float(np.mean(centroid_frames)) if centroid_frames else None
    result["sub_bass_ratio"] = float(np.mean(sub_bass_frames)) if sub_bass_frames else None
    result["high_freq_ratio"] = float(np.mean(high_freq_frames)) if high_freq_frames else None
    result["all_peak_freqs"] = all_peak_freqs
    result["all_peak_mags"] = all_peak_mags

    return result


# ---------------------------------------------------------------------------
# ML models
# ---------------------------------------------------------------------------


def _load_labels(json_path: Path) -> list[str]:
    """Read the 'classes' list from a model metadata JSON. Returns [] on failure."""
    try:
        with open(json_path) as f:
            return json.load(f).get("classes", [])
    except Exception as exc:
        logger.warning("Could not load labels from %s: %s", json_path, exc)
        return []


def _run_classifier(
    es_module,
    pb_path: Path,
    embeddings,
    output_node: str,
    label: str,
) -> np.ndarray | None:
    """
    Run a TensorflowPredict2D classification head against pre-computed embeddings.
    Returns mean output vector (1-D) or None on failure.
    """
    if not pb_path.exists():
        logger.warning("%s model file not found: %s", label, pb_path)
        return None
    if embeddings is None:
        logger.warning("%s skipped: EffNet embeddings unavailable", label)
        return None
    try:
        model = es_module.TensorflowPredict2D(
            graphFilename=str(pb_path),
            output=output_node,
        )
        return np.mean(model(embeddings), axis=0)
    except Exception as exc:
        logger.warning("%s failed: %s", label, exc)
        return None


def _run_embedding_model(
    es_module,
    pb_path: Path,
    audio_16k,
    label: str,
) -> list[float] | None:
    """
    Run a Discogs-EffNet embedding variant model.
    Returns mean embedding vector as a list or None on failure.
    """
    if not pb_path.exists():
        logger.warning("%s model file not found: %s", label, pb_path)
        return None
    try:
        model = es_module.TensorflowPredictEffnetDiscogs(
            graphFilename=str(pb_path),
        )
        raw = model(audio_16k)  # (batch, 1280)
        return np.mean(raw, axis=0).tolist()
    except Exception as exc:
        logger.warning("%s failed: %s", label, exc)
        return None


def _run_ml_models(audio_16k, config: EssentiaConfig) -> dict:
    """
    Run all TensorFlow ML models and return their output keys.

    Must only be called when _TF_AVAILABLE is True and config.run_ml_models is True.
    Each model is independent — a failure in one does not abort the others.
    """
    import essentia.standard as es

    result = {
        "genre_probabilities": None,
        "genre_top_labels": None,
        "embedding": None,
        "embedding_track": None,
        "embedding_artist": None,
        "embedding_label": None,
        "embedding_release": None,
        "arousal": None,
        "valence": None,
        "mood_aggressive": None,
        "mood_happy": None,
        "mood_party": None,
        "mood_relaxed": None,
        "mood_sad": None,
        "ml_danceability": None,
        "instrument_probabilities": None,
        "instrument_top_labels": None,
        "moodtheme_probabilities": None,
        "moodtheme_top_labels": None,
        "voice_probability": None,
        "voice_probability_musicnn": None,
    }

    # --- Discogs-EffNet backbone: classification + embeddings (one forward pass) ---
    effnet_pb = config.model_dir / "discogs-effnet-bs64-1.pb"
    effnet_json = config.model_dir / "discogs-effnet-bs64-1.json"

    effnet_embeddings = None  # (batch, 1280) — reused by all classification heads below

    if not effnet_pb.exists():
        logger.warning("EffNet model file not found: %s", effnet_pb)
    else:
        try:
            # Classification pass — output is (batch, 400)
            effnet_cls = es.TensorflowPredictEffnetDiscogs(graphFilename=str(effnet_pb))
            predictions_raw = effnet_cls(audio_16k)
            predictions = np.mean(predictions_raw, axis=0)
            result["genre_probabilities"] = predictions.tolist()

            if effnet_json.exists():
                with open(effnet_json) as f:
                    meta = json.load(f)
                labels = meta.get("classes", [])
                top_indices = np.argsort(predictions)[::-1][: config.genre_top_n]
                result["genre_top_labels"] = [labels[i] for i in top_indices]
            else:
                logger.warning("EffNet metadata JSON not found: %s", effnet_json)

            # Embedding pass — find layer name from metadata JSON
            embedding_layer = None
            if effnet_json.exists():
                with open(effnet_json) as f:
                    meta = json.load(f)
                for out in meta.get("schema", {}).get("outputs", []):
                    if out.get("output_purpose") == "embeddings":
                        embedding_layer = out.get("name")
                        break

            if embedding_layer:
                effnet_emb = es.TensorflowPredictEffnetDiscogs(
                    graphFilename=str(effnet_pb),
                    output=embedding_layer,
                )
                # Keep raw (batch, 1280) for downstream classification heads.
                effnet_embeddings = effnet_emb(audio_16k)
                result["embedding"] = np.mean(effnet_embeddings, axis=0).tolist()
            else:
                logger.warning(
                    "Could not determine EffNet embedding layer from metadata; "
                    "embedding will be None"
                )

        except Exception as exc:
            logger.warning("EffNet model failed: %s", exc)

    # --- Mood: arousal/valence (DEAM via MusiCNN) ---
    # DEAM requires MusiCNN embeddings, not EffNet.
    # Pipeline: audio_16k -> TensorflowPredictMusiCNN -> TensorflowPredict2D -> [arousal, valence]
    deam_pb = config.model_dir / "deam-msd-musicnn-2.pb"
    musicnn_pb = config.model_dir / "msd-musicnn-1.pb"

    musicnn_embeddings = None  # (batch, N) — also reused by MusiCNN voice classifier

    if not deam_pb.exists():
        logger.warning("DEAM mood model file not found: %s", deam_pb)
    elif not musicnn_pb.exists():
        logger.warning("MusiCNN model file not found (required for DEAM): %s", musicnn_pb)
    else:
        try:
            musicnn = es.TensorflowPredictMusiCNN(
                graphFilename=str(musicnn_pb),
                output="model/dense/BiasAdd",
            )
            musicnn_embeddings = musicnn(audio_16k)
            mood_model = es.TensorflowPredict2D(
                graphFilename=str(deam_pb),
                output="model/Identity",
            )
            mood_output = np.mean(mood_model(musicnn_embeddings), axis=0)
            result["arousal"] = float(mood_output[0])
            result["valence"] = float(mood_output[1])
        except Exception as exc:
            logger.warning("DEAM mood model failed: %s", exc)

    # --- Binary mood classifiers (all take EffNet embeddings, output model/Sigmoid) ---
    mood_models = [
        ("mood_aggressive", "mood_aggressive-discogs-effnet-1.pb"),
        ("mood_happy", "mood_happy-discogs-effnet-1.pb"),
        ("mood_party", "mood_party-discogs-effnet-1.pb"),
        ("mood_relaxed", "mood_relaxed-discogs-effnet-1.pb"),
        ("mood_sad", "mood_sad-discogs-effnet-1.pb"),
    ]
    for key, filename in mood_models:
        out = _run_classifier(
            es, config.model_dir / filename, effnet_embeddings, "model/Softmax", key
        )
        if out is not None:
            result[key] = float(out[1])  # index 1 = "yes" probability

    # --- ML danceability (EffNet embeddings, output model/Softmax) ---
    # Class order confirmed from Essentia metadata: ["danceable", "not_danceable"]
    # so index 0 is the "danceable" probability.
    dance_out = _run_classifier(
        es,
        config.model_dir / "danceability-discogs-effnet-1.pb",
        effnet_embeddings,
        "model/Softmax",
        "ml_danceability",
    )
    if dance_out is not None:
        result["ml_danceability"] = float(dance_out[0])  # index 0 = "danceable"

    # --- MTG-Jamendo instrument classifier (40 classes, multi-label) ---
    instrument_pb = config.model_dir / "mtg_jamendo_instrument-discogs-effnet-1.pb"
    instrument_json = config.model_dir / "mtg_jamendo_instrument-discogs-effnet-1.json"
    inst_out = _run_classifier(es, instrument_pb, effnet_embeddings, "model/Sigmoid", "instrument")
    if inst_out is not None:
        result["instrument_probabilities"] = inst_out.tolist()
        instrument_labels = _load_labels(instrument_json)
        if instrument_labels:
            top_indices = np.argsort(inst_out)[::-1][: config.genre_top_n]
            result["instrument_top_labels"] = [instrument_labels[i] for i in top_indices]

    # --- MTG-Jamendo mood/theme classifier (56 classes, multi-label) ---
    moodtheme_pb = config.model_dir / "mtg_jamendo_moodtheme-discogs-effnet-1.pb"
    moodtheme_json = config.model_dir / "mtg_jamendo_moodtheme-discogs-effnet-1.json"
    mt_out = _run_classifier(es, moodtheme_pb, effnet_embeddings, "model/Sigmoid", "moodtheme")
    if mt_out is not None:
        result["moodtheme_probabilities"] = mt_out.tolist()
        moodtheme_labels = _load_labels(moodtheme_json)
        if moodtheme_labels:
            top_indices = np.argsort(mt_out)[::-1][: config.genre_top_n]
            result["moodtheme_top_labels"] = [moodtheme_labels[i] for i in top_indices]

    # --- Voice/Instrumental classifiers ---
    # EffNet-based (already working)
    voice_pb = config.model_dir / "voice_instrumental-discogs-effnet-1.pb"
    voice_out = _run_classifier(es, voice_pb, effnet_embeddings, "model/Softmax", "voice (effnet)")
    if voice_out is not None:
        result["voice_probability"] = float(voice_out[1])

    # MusiCNN-based voice classifier — full model taking audio_16k directly,
    # not a classification head. Uses TensorflowPredictMusiCNN like the DEAM pipeline.
    voice_musicnn_pb = config.model_dir / "voice_instrumental-musicnn-msd-2.pb"
    if not voice_musicnn_pb.exists():
        logger.warning("MusiCNN voice model file not found: %s", voice_musicnn_pb)
    else:
        try:
            voice_musicnn_model = es.TensorflowPredictMusiCNN(
                graphFilename=str(voice_musicnn_pb),
                output="model/Sigmoid",
            )
            voice_musicnn_raw = voice_musicnn_model(audio_16k)  # (batch, 2)
            voice_musicnn_out = np.mean(voice_musicnn_raw, axis=0)
            result["voice_probability_musicnn"] = float(voice_musicnn_out[1])
        except Exception as exc:
            logger.warning("voice (musicnn) failed: %s", exc)

    # --- Discogs embedding variants (each is a separate EffNet variant model) ---
    embedding_models = [
        ("embedding_track", "discogs_track_embeddings-effnet-bs64-1.pb"),
        ("embedding_artist", "discogs_artist_embeddings-effnet-bs64-1.pb"),
        ("embedding_label", "discogs_label_embeddings-effnet-bs64-1.pb"),
        ("embedding_release", "discogs_release_embeddings-effnet-bs64-1.pb"),
    ]
    for key, filename in embedding_models:
        result[key] = _run_embedding_model(es, config.model_dir / filename, audio_16k, key)

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyse_track(file_path: str, config: EssentiaConfig) -> dict:
    """
    Extract raw audio features from a single file using Essentia.

    Returns a flat dict. Never raises — failures are returned as structured
    data. See module docstring for the full return contract.
    """
    try:
        return _analyse_track_inner(file_path, config)
    except Exception as exc:
        logger.exception("Unexpected top-level error analysing %s", file_path)
        result = _null_result()
        result["analysis_error"] = str(exc)
        return result


def _analyse_track_inner(file_path: str, config: EssentiaConfig) -> dict:
    import essentia.standard as es

    result = {k: None for k in _ALL_KEYS}
    result.update(_meta_fields())

    # --- Audio loading ---
    try:
        audio_44k = es.MonoLoader(filename=file_path, sampleRate=44100)()
    except Exception as exc:
        logger.error("MonoLoader failed for %s: %s", file_path, exc)
        result["analysis_error"] = str(exc)
        return result

    # Stereo version derived from mono (no second disk read)
    try:
        audio_stereo = es.StereoMuxer()(audio_44k, audio_44k)
    except Exception as exc:
        logger.warning("StereoMuxer failed: %s", exc)
        audio_stereo = None

    # 16 kHz mono for ML models
    audio_16k = None
    if config.run_ml_models and _TF_AVAILABLE:
        try:
            audio_16k = es.MonoLoader(filename=file_path, sampleRate=16000)()
        except Exception as exc:
            logger.warning("16 kHz load failed: %s", exc)

    # --- Frame-level processing ---
    try:
        frame_results = _run_frame_loop(audio_44k)
        result["spectral_centroid_hz"] = frame_results["spectral_centroid_hz"]
        result["sub_bass_ratio"] = frame_results["sub_bass_ratio"]
        result["high_freq_ratio"] = frame_results["high_freq_ratio"]
        result["mfcc_mean"] = frame_results["mfcc_mean"]
        result["mfcc_var"] = frame_results["mfcc_var"]
        result["bark_bands_mean"] = frame_results["bark_bands_mean"]
        all_peak_freqs = frame_results["all_peak_freqs"]
        all_peak_mags = frame_results["all_peak_mags"]
    except Exception as exc:
        logger.warning("Frame loop failed: %s", exc)
        all_peak_freqs = []
        all_peak_mags = []

    # --- TuningFrequency (uses accumulated spectral peaks from frame loop) ---
    try:
        if all_peak_freqs:
            tuning_alg = es.TuningFrequency()
            tf_freq, tf_cents = tuning_alg(
                np.array(all_peak_freqs, dtype="float32"),
                np.array(all_peak_mags, dtype="float32"),
            )
            result["tuning_frequency_hz"] = float(tf_freq)
            result["tuning_cents"] = float(tf_cents)
    except Exception as exc:
        logger.warning("TuningFrequency failed: %s", exc)

    # --- RhythmExtractor2013 ---
    try:
        rhythm = es.RhythmExtractor2013(
            method="multifeature",
            minTempo=config.min_tempo,
            maxTempo=config.max_tempo,
        )
        bpm, ticks, confidence, estimates, bpm_intervals = rhythm(audio_44k)
        result["bpm"] = float(bpm)
        result["beat_ticks"] = ticks.tolist()
        result["bpm_confidence"] = float(confidence)
        result["bpm_estimates"] = estimates.tolist()
        result["bpm_intervals"] = bpm_intervals.tolist()
    except Exception as exc:
        logger.warning("RhythmExtractor2013 failed: %s", exc)

    # --- Danceability ---
    try:
        dance_alg = es.Danceability()
        danceability, dfa = dance_alg(audio_44k)
        result["danceability"] = float(danceability)
        result["danceability_dfa"] = dfa.tolist()
    except Exception as exc:
        logger.warning("Danceability failed: %s", exc)

    # --- KeyExtractor ---
    try:
        key_alg = es.KeyExtractor(profileType="edma")
        key, scale, strength = key_alg(audio_44k)
        result["key"] = key
        result["key_scale"] = scale
        result["key_strength"] = float(strength)
    except Exception as exc:
        logger.warning("KeyExtractor failed: %s", exc)

    # --- LoudnessEBUR128 ---
    if audio_stereo is not None:
        try:
            loudness_alg = es.LoudnessEBUR128()
            momentary, short_term, integrated, lrange = loudness_alg(audio_stereo)
            result["momentary_loudness"] = momentary.tolist()
            result["short_term_loudness"] = short_term.tolist()
            result["integrated_loudness"] = float(integrated)
            result["loudness_range"] = float(lrange)
        except Exception as exc:
            logger.warning("LoudnessEBUR128 failed: %s", exc)

    # --- DynamicComplexity ---
    try:
        dc_alg = es.DynamicComplexity()
        dynamic_complexity, dc_loudness = dc_alg(audio_44k)
        result["dynamic_complexity"] = float(dynamic_complexity)
        result["dynamic_complexity_loudness"] = float(dc_loudness)
    except Exception as exc:
        logger.warning("DynamicComplexity failed: %s", exc)

    # --- OnsetRate ---
    try:
        onset_alg = es.OnsetRate()
        onsets, onset_rate = onset_alg(audio_44k)
        result["onset_times"] = onsets.tolist()
        result["onset_rate"] = float(onset_rate)
    except Exception as exc:
        logger.warning("OnsetRate failed: %s", exc)

    # --- PredominantPitchMelodia (optional — slow) ---
    if config.run_pitch_analysis:
        try:
            pitch_alg = es.PredominantPitchMelodia()
            pitch, pitch_conf = pitch_alg(audio_44k)
            result["pitch_frames"] = pitch.tolist()
            result["pitch_confidence_frames"] = pitch_conf.tolist()
        except Exception as exc:
            logger.warning("PredominantPitchMelodia failed: %s", exc)

    # --- ML models ---
    if _TF_AVAILABLE and config.run_ml_models:
        if audio_16k is not None:
            try:
                ml_results = _run_ml_models(audio_16k, config)
                result.update(ml_results)
            except Exception as exc:
                logger.warning("_run_ml_models failed: %s", exc)
        else:
            logger.warning("ML models skipped: 16 kHz audio unavailable")

    return result
