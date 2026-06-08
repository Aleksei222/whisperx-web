import logging

import numpy as np

log = logging.getLogger(__name__)


class WhisperTranscriber:
    def __init__(self, model_size: str, device: str, compute_type: str):
        import faster_whisper

        log.info(f"Loading Whisper {model_size} on {device} ({compute_type})...")

        # BatchedInferencePipeline даёт x2-3 скорость на GPU
        base = faster_whisper.WhisperModel(
            model_size, device=device, compute_type=compute_type,
        )
        if device == "cuda":
            self._pipeline = faster_whisper.BatchedInferencePipeline(base)
            self._batched = True
            log.info("Using BatchedInferencePipeline (GPU)")
        else:
            self._pipeline = base
            self._batched = False
            log.info("Using standard pipeline (CPU)")

    def transcribe(self, audio: np.ndarray,
                   language: str | None = None,
                   batch_size: int = 16) -> tuple[list[dict], str]:
        """
        Возвращает (words, detected_language).
        words: [{"word": str, "start": float, "end": float}]
        """
        kwargs = dict(language=language, word_timestamps=True)

        if self._batched:
            segments_iter, info = self._pipeline.transcribe(
                audio, batch_size=batch_size, **kwargs
            )
        else:
            segments_iter, info = self._pipeline.transcribe(
                audio, vad_filter=True, **kwargs
            )

        words = []
        for seg in segments_iter:
            if not seg.words:
                continue
            for w in seg.words:
                word = w.word.strip()
                if word:
                    words.append({
                        "word":  word,
                        "start": round(w.start, 3),
                        "end":   round(w.end, 3),
                    })

        log.info(f"Transcribed {len(words)} words, language={info.language} "
                 f"(p={info.language_probability:.2f})")
        return words, info.language