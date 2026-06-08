"""
WhisperX Web — FastAPI backend
"""

import os
import sys

if sys.platform == "win32":
    import site
    # Поиск путей к библиотекам nvidia внутри виртуального окружения
    for sp in site.getsitepackages():
        for pkg in ["cudnn", "cublas"]:
            bin_path = os.path.join(sp, "nvidia", pkg, "bin")
            if os.path.exists(bin_path):
                # Добавляем в PATH для старых механизмов загрузки DLL
                os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                # Добавляем в DLL directory для Python 3.8+
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(bin_path)
                    

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
import wave
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from pipeline import process
from formatting import fmt_json, fmt_srt, fmt_txt

log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="WhisperX Web", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

# ── Globals ───────────────────────────────────────────────────────────────────
_whisper  = None
_diarizer = None
_args     = None

AUDIO_EXTENSIONS = {
    "mp3", "wav", "flac", "m4a", "ogg", "opus",
    "aac", "wma", "webm", "mp4", "mkv",
}
UPLOAD_DIR = Path(tempfile.gettempdir()) / "whisperx_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def get_models():
    if _whisper is None or _diarizer is None:
        raise HTTPException(503, "Models not loaded yet.")
    return _whisper, _diarizer


def _build_response(result: dict) -> dict:
    utterances = result["utterances"]
    return {
        "language":   result["language"],
        "duration":   result["duration"],
        "utterances": utterances,
        "stats": {
            "speakers":   len({u["speaker_label"] for u in utterances}),
            "utterances": len(utterances),
            "words":      sum(len(u.get("words", [])) for u in utterances),
        },
    }


def _run_pipeline(audio_path: str, language: str, num_speakers: int) -> dict:
    whisper, diarizer = get_models()
    return process(
        audio_path, whisper, diarizer,
        num_speakers=num_speakers,
        gap=getattr(_args, "gap", 1.5),
        language=language or None,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(Path("templates/index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "models_loaded": _whisper is not None,
        "device": getattr(_args, "device", "unknown"),
        "model":  getattr(_args, "model",  "unknown"),
        "yandex_token_set": bool(getattr(_args, "yandex_token", "")),
    }


# ── 1. File upload → transcribe ───────────────────────────────────────────────
@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(default=""),
    num_speakers: int = Form(default=0),
):
    ext = Path(file.filename or "file.mp3").suffix.lstrip(".").lower() or "mp3"
    if ext not in AUDIO_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: .{ext}")

    job_id    = uuid.uuid4().hex
    audio_path = UPLOAD_DIR / f"{job_id}.{ext}"
    content   = await file.read()
    audio_path.write_bytes(content)
    log.info(f"Upload job {job_id}: {file.filename} ({len(content)/1e6:.1f} MB)")

    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_pipeline(str(audio_path), language, num_speakers)
        )
    except Exception as e:
        log.exception("Processing failed")
        raise HTTPException(500, f"Processing failed: {e}")
    finally:
        audio_path.unlink(missing_ok=True)

    return JSONResponse(_build_response(result))


# ── 2. URL download (YouTube / SoundCloud / etc.) → transcribe ────────────────
@app.post("/transcribe/url")
async def transcribe_url(body: dict):
    url          = (body.get("url") or "").strip()
    language     = body.get("language", "")
    num_speakers = int(body.get("num_speakers", 0))

    if not url:
        raise HTTPException(400, "url is required")

    from audio.sources import get_source
    yandex_token = getattr(_args, "yandex_token", "") or ""

    job_dir = UPLOAD_DIR / uuid.uuid4().hex
    job_dir.mkdir()

    try:
        source = get_source(url, yandex_token)
        audio_path, title = await asyncio.get_running_loop().run_in_executor(
            None, lambda: source.fetch(url, str(job_dir))
        )
        log.info(f"URL job: '{title}' → {audio_path}")

        result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: _run_pipeline(audio_path, language, num_speakers)
        )
    except Exception as e:
        log.exception("URL processing failed")
        raise HTTPException(500, str(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    resp = _build_response(result)
    resp["source_title"] = title
    return JSONResponse(resp)


# ── 3. Microphone recording via WebSocket ─────────────────────────────────────
#
# Протокол:
#   Client → Server: бинарные PCM-фреймы (16-bit signed LE, 16 kHz, mono)
#   Client → Server: текстовое сообщение "stop:<language>:<num_speakers>"
#   Server → Client: JSON с результатом транскрипции
#
@app.websocket("/ws/record")
async def ws_record(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket: microphone session started")

    pcm_chunks = []
    sample_rate = 16_000  # фронт шлёт 16 kHz

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break

            # Бинарный фрейм — PCM-данные
            if "bytes" in msg and msg["bytes"]:
                pcm_chunks.append(msg["bytes"])
                continue

            # Текстовая команда
            if "text" in msg and msg["text"]:
                text = msg["text"]
                if text.startswith("stop:"):
                    parts     = text.split(":", 2)
                    language  = parts[1] if len(parts) > 1 else ""
                    num_spk   = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                    break

        if not pcm_chunks:
            await ws.send_json({"error": "No audio received"})
            return

        # Сохраняем в WAV
        job_id    = uuid.uuid4().hex
        wav_path  = UPLOAD_DIR / f"{job_id}_mic.wav"
        raw_pcm   = b"".join(pcm_chunks)

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)   # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(raw_pcm)

        duration_s = len(raw_pcm) / 2 / sample_rate
        log.info(f"Mic job {job_id}: {duration_s:.1f}s of audio")

        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: _run_pipeline(str(wav_path), language, num_spk)
            )
            await ws.send_json(_build_response(result))
        except Exception as e:
            log.exception("Mic processing failed")
            await ws.send_json({"error": str(e)})
        finally:
            wav_path.unlink(missing_ok=True)

    except WebSocketDisconnect:
        log.info("WebSocket: client disconnected")


# ── 4. Export ─────────────────────────────────────────────────────────────────
@app.post("/export/{fmt}")
async def export(fmt: str, body: dict):
    utterances = body.get("utterances", [])
    if fmt == "srt":
        content, media_type, filename = fmt_srt(utterances).encode(), "text/plain", "subtitles.srt"
    elif fmt == "txt":
        content, media_type, filename = fmt_txt(utterances).encode(), "text/plain", "transcript.txt"
    elif fmt == "json":
        content, media_type, filename = fmt_json(body).encode(), "application/json", "transcript.json"
    else:
        raise HTTPException(400, f"Unknown format: {fmt}")
    return Response(content=content, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--model", default="small",
                   choices=["tiny","base","small","medium","large-v2","large-v3","turbo"])
    p.add_argument("--device", default="auto", choices=["auto","cpu","cuda"])
    p.add_argument("--compute-type", default="auto",
                   choices=["auto","float16","int8_float16","int8"])
    p.add_argument("--gap", type=float, default=1.5)
    p.add_argument("--chunk-duration", type=float, default=10.0)
    p.add_argument("--chunk-step",     type=float, default=2.5)
    p.add_argument("--onnx-device", default="auto", choices=["auto","cpu","cuda"])
    p.add_argument("--hf-cache", default=".cache/hf")
    p.add_argument("--yandex-token", default="",
                   help="Токен Яндекс.Музыки (опционально)")
    args = p.parse_args()

    if args.device == "auto":
        try:
            import torch
            args.device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            args.device = "cpu"
    if args.compute_type == "auto":
        args.compute_type = "float16" if args.device == "cuda" else "int8"
    if args.onnx_device == "auto":
        args.onnx_device = args.device

    global _args
    _args = args

    from models import WhisperTranscriber, Diarizer, PyannoteONNX
    from huggingface_hub import snapshot_download

    log.info(f"Device: {args.device}, compute: {args.compute_type}")
    global _whisper, _diarizer

    _whisper = WhisperTranscriber(args.model, args.device, args.compute_type)

    repo_dir = snapshot_download(
        "welcomyou/pyannote-community-1-onnx-split", cache_dir=args.hf_cache
    )
    _diarizer = Diarizer(
        PyannoteONNX(repo_dir, device=args.onnx_device),
        chunk_duration=args.chunk_duration,
        chunk_step=args.chunk_step,
    )

    log.info(f"Server: http://{args.host}:{args.port}")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()