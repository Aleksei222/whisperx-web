import logging
import os
import tempfile

import numpy as np

SAMPLE_RATE = 16_000
log = logging.getLogger(__name__)


def load_audio(path: str) -> np.ndarray:
    """Любой формат → mono float32 @ 16 kHz."""
    try:
        import librosa
        audio, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
        log.debug(f"Loaded via librosa: {len(audio)} samples")
        return audio.astype(np.float32)
    except Exception as e:
        log.debug(f"librosa failed ({e}), trying ffmpeg")

    return _load_via_ffmpeg(path)


def _load_via_ffmpeg(path: str) -> np.ndarray:
    import subprocess
    import wave

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path,
             "-ar", str(SAMPLE_RATE), "-ac", "1",
             "-f", "wav", tmp.name],
            check=True, capture_output=True,
        )
        with wave.open(tmp.name) as wf:
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        log.debug(f"Loaded via ffmpeg: {len(samples)} samples")
        return samples
    finally:
        os.unlink(tmp.name)


def duration_seconds(audio: np.ndarray) -> float:
    return len(audio) / SAMPLE_RATE