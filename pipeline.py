import logging

import numpy as np

from audio import load_audio, duration_seconds
from models import WhisperTranscriber, Diarizer

log = logging.getLogger(__name__)


def assign_speaker(word_start: float, word_end: float,
                   diarization: list[dict]) -> int:
    """Возвращает speaker с максимальным перекрытием с [word_start, word_end].

    diarization должен быть отсортирован по start (гарантируется в
    group_utterances). Ранний выход безопасен только после сортировки.
    """
    best_spk, best_overlap = 0, -1.0
    for seg in diarization:
        if seg["start"] >= word_end:
            # Список отсортирован — дальше перекрытий не будет
            break
        overlap = min(seg["end"], word_end) - max(seg["start"], word_start)
        if overlap > best_overlap:
            best_overlap, best_spk = overlap, seg["speaker"]
    return best_spk


def group_utterances(words: list[dict], diarization: list[dict],
                     gap: float = 1.5) -> list[dict]:
    if not words:
        return []

    # Гарантируем сортировку — assign_speaker зависит от неё
    diarization = sorted(diarization, key=lambda s: s["start"])

    utterances, buf, buf_spk = [], [], assign_speaker(
        words[0]["start"], words[0]["end"], diarization
    )

    for w in words:
        spk   = assign_speaker(w["start"], w["end"], diarization)
        pause = (w["start"] - buf[-1]["end"]) if buf else 0.0
        if buf and (spk != buf_spk or pause > gap):
            _flush(buf, buf_spk, utterances)
            buf, buf_spk = [], spk
        buf.append(w)

    if buf:
        _flush(buf, buf_spk, utterances)

    # readable labels
    seen, nxt = {}, 1
    for u in utterances:
        if u["speaker"] not in seen:
            seen[u["speaker"]] = f"SPEAKER_{nxt:02d}"
            nxt += 1
        u["speaker_label"] = seen[u["speaker"]]

    return utterances


def _flush(buf, spk, out):
    text = " ".join(x["word"] for x in buf).strip()
    if text:
        out.append({
            "start":   buf[0]["start"],
            "end":     buf[-1]["end"],
            "speaker": spk,
            "words":   list(buf),   # сохраняем слова для кликабельного плеера
            "text":    text,
            "speaker_label": "",
        })


def process(audio_path: str,
            whisper: WhisperTranscriber,
            diarizer: Diarizer,
            num_speakers: int = 0,
            gap: float = 1.5,
            language: str | None = None) -> dict:

    log.info(f"Loading: {audio_path}")
    audio    = load_audio(audio_path)
    duration = duration_seconds(audio)
    log.info(f"Duration: {duration:.1f}s")

    log.info("Transcribing...")
    words, lang = whisper.transcribe(audio, language=language)

    log.info("Diarizing...")
    diarization = diarizer.diarize(audio, num_speakers=num_speakers)

    log.info("Grouping utterances...")
    utterances = group_utterances(words, diarization, gap=gap)

    return {
        "language":   lang,
        "duration":   round(duration, 2),
        "utterances": utterances,
    }
