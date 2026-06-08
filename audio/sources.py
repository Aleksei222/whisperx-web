"""
Источники аудио. Сейчас только заглушки.
Позже: скачивание с Я.Музыки, YouTube, SoundCloud и т.д.
"""
import logging
import os
import re
import tempfile
import uuid

log = logging.getLogger(__name__)


class AudioSource:
    def fetch(self, url: str, output_dir: str) -> tuple[str, str]:
        """Скачать аудио → (path, title)."""
        raise NotImplementedError


# ── YouTube / SoundCloud / любой yt-dlp источник ─────────────────────────────

class YtDlpSource(AudioSource):
    """Скачивание через yt-dlp (YouTube, SoundCloud, Vimeo и др.)"""

    def fetch(self, url: str, output_dir: str) -> tuple[str, str]:
        import yt_dlp

        out_template = os.path.join(output_dir, "%(id)s.%(ext)s")
        title_holder = {}

        class InfoHook:
            def __init__(self): self.title = ""
            def __call__(self, d):
                if d.get("status") == "finished":
                    title_holder["title"] = d.get("info_dict", {}).get("title", "")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [InfoHook()],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", url)

        # Находим скачанный mp3
        for f in os.listdir(output_dir):
            if f.endswith(".mp3"):
                return os.path.join(output_dir, f), title

        raise RuntimeError("yt-dlp: output mp3 not found")


# ── Яндекс.Музыка ────────────────────────────────────────────────────────────

class YandexMusicSource(AudioSource):
    """
    Скачивание треков с Яндекс.Музыки через yandex-music-api.
    Требует токен аккаунта.
    """

    def __init__(self, token: str):
        if not token:
            raise ValueError("Яндекс.Музыка: токен не задан")
        self.token = token

    def fetch(self, url: str, output_dir: str) -> tuple[str, str]:
        from yandex_music import Client

        client = Client(self.token).init()

        # Извлекаем track_id из URL вида:
        # https://music.yandex.ru/album/1234/track/5678
        # https://music.yandex.ru/track/5678
        match = re.search(r"track[s]?/(\d+)", url)
        if not match:
            # Может быть просто числовой ID
            if url.strip().isdigit():
                track_id = url.strip()
            else:
                raise ValueError(f"Не удалось извлечь ID трека из URL: {url}")
        else:
            track_id = match.group(1)

        track = client.tracks([track_id])[0]
        title = f"{track.artists[0].name} — {track.title}" if track.artists else track.title

        out_path = os.path.join(output_dir, f"{uuid.uuid4().hex}.mp3")
        track.download(out_path)
        log.info(f"Яндекс.Музыка: скачан '{title}' → {out_path}")
        return out_path, title


# ── Роутер ────────────────────────────────────────────────────────────────────

def get_source(url: str, yandex_token: str = "") -> AudioSource:
    if "music.yandex" in url or url.strip().isdigit():
        return YandexMusicSource(yandex_token)
    # yt-dlp умеет YouTube, youtu.be, SoundCloud, Vimeo и ещё ~1000 сайтов
    return YtDlpSource()