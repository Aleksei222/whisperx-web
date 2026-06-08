import logging
import os

import numpy as np

from audio import SAMPLE_RATE

log = logging.getLogger(__name__)

EMB_DIM    = 256
STATS_DIM  = 5120
SEG_FRAMES = 998   # 10s @ 16kHz/hop160


class PyannoteONNX:
    def __init__(self, model_dir: str, device: str = "cpu"):
        import onnxruntime as ort

        if device == "cuda":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 4
        opts.intra_op_num_threads = 4
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        emb_path = os.path.join(model_dir, "embedding_encoder.onnx")
        w_path   = os.path.join(model_dir, "resnet_seg_1_weight.npy")
        b_path   = os.path.join(model_dir, "resnet_seg_1_bias.npy")

        for p in [emb_path, w_path, b_path]:
            if not os.path.exists(p):
                raise FileNotFoundError(f"Missing: {p}")

        self.session    = ort.InferenceSession(emb_path, opts, providers=providers)
        self.W          = np.load(w_path)   # (256, 5120)
        self.b          = np.load(b_path)   # (256,)
        self.input_name = self.session.get_inputs()[0].name

        actual = self.session.get_providers()[0]
        log.info(f"PyannoteONNX loaded, provider={actual}")

    def _fbank(self, audio: np.ndarray) -> np.ndarray:
        """audio (N,) → (SEG_FRAMES, 80) log-mel.

        Используем натуральный логарифм (ln) — именно так обучена pyannote.
        librosa.power_to_db возвращает dB (10*log10), что даёт другое
        распределение признаков. Поэтому считаем вручную через ln.
        """
        try:
            import librosa
            mel = librosa.feature.melspectrogram(
                y=audio, sr=SAMPLE_RATE,
                n_fft=512, hop_length=160, win_length=400,
                n_mels=80, fmin=20.0, fmax=7600.0, power=2.0,
            )
            # ln(mel), как в оригинальном pyannote/speechbrain
            fb = np.log(np.maximum(mel, 1e-10)).T.astype(np.float32)
        except ImportError:
            fb = self._fbank_numpy(audio)

        # pad / trim
        T = fb.shape[0]
        if T < SEG_FRAMES:
            fb = np.pad(fb, ((0, SEG_FRAMES - T), (0, 0)))
        return fb[:SEG_FRAMES]

    def _fbank_numpy(self, audio: np.ndarray) -> np.ndarray:
        """Fallback без librosa. Использует ln для совместимости с _fbank."""
        n_mels, hop, win, fft = 80, 160, 400, 512
        hann = 0.5 * (1 - np.cos(2 * np.pi * np.arange(win) / (win - 1)))
        n = len(audio)
        frames = max(1, (n - win) // hop + 1)

        hz2mel = lambda f: 2595 * np.log10(1 + f / 700)
        mel2hz = lambda m: 700 * (10 ** (m / 2595) - 1)
        mel_pts = mel2hz(np.linspace(hz2mel(20), hz2mel(7600), n_mels + 2))
        bins = np.floor((fft + 1) * mel_pts / SAMPLE_RATE).astype(int)
        n_bins = fft // 2 + 1
        fb_mat = np.zeros((n_mels, n_bins), dtype=np.float32)
        for m in range(1, n_mels + 1):
            for k in range(bins[m - 1], bins[m]):
                fb_mat[m-1, k] = (k - bins[m-1]) / max(bins[m] - bins[m-1], 1)
            for k in range(bins[m], bins[m + 1]):
                fb_mat[m-1, k] = (bins[m+1] - k) / max(bins[m+1] - bins[m], 1)

        result = np.zeros((frames, n_mels), dtype=np.float32)
        for i in range(frames):
            frame = audio[i*hop: i*hop+win]
            if len(frame) < win:
                frame = np.pad(frame, (0, win - len(frame)))
            spec = np.abs(np.fft.rfft(frame * hann, n=fft)) ** 2
            # ln, не log10 — совместимо с librosa-веткой
            result[i] = np.log(np.maximum(fb_mat @ spec, 1e-10))
        return result

    def embed(self, audio_chunk: np.ndarray) -> np.ndarray:
        """audio (N,) → (256,) L2-нормированный embedding."""
        fb  = self._fbank(audio_chunk)[np.newaxis].astype(np.float32)  # (1,998,80)
        out = self.session.run(None, {self.input_name: fb})[0][0]      # (2560, F)
        stats = np.concatenate([out.mean(axis=1), out.std(axis=1)])    # (5120,)
        emb   = stats @ self.W.T + self.b                              # (256,)
        norm  = np.linalg.norm(emb) + 1e-8
        return (emb / norm).astype(np.float32)


class Diarizer:
    def __init__(self, model: PyannoteONNX,
                 chunk_duration: float = 10.0,
                 chunk_step: float = 2.5):
        self.model          = model
        self.chunk_duration = chunk_duration
        self.chunk_step     = chunk_step

    def diarize(self, audio: np.ndarray,
                num_speakers: int = 0) -> list[dict]:
        """→ [{\"start\": float, \"end\": float, \"speaker\": int}], отсортировано по start."""
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score

        duration = len(audio) / SAMPLE_RATE
        windows  = self._windows(duration)
        log.info(f"Diarizing {len(windows)} chunks ({duration:.1f}s)...")

        embeddings = []
        for s, e in windows:
            chunk = audio[int(s * SAMPLE_RATE): int(e * SAMPLE_RATE)]
            emb   = self.model.embed(chunk) if len(chunk) >= 1600 \
                    else np.zeros(EMB_DIM, dtype=np.float32)
            embeddings.append(emb)

        X = np.array(embeddings)
        n = len(X)

        if n == 1:
            log.info("Single chunk → single speaker")
            return [{"start": windows[0][0], "end": windows[0][1], "speaker": 0}]

        # Максимум 6 спикеров: silhouette нестабилен при больших k / малых n
        max_k = min(6, n - 1)

        if num_speakers == 0:
            if max_k < 2:
                return [{"start": s, "end": e, "speaker": 0} for s, e in windows]

            best_k, best_sc = 2, -1.0
            for k in range(2, max_k + 1):
                lbls = AgglomerativeClustering(
                    n_clusters=k, metric="cosine", linkage="average"
                ).fit_predict(X)
                if len(set(lbls)) < 2:
                    continue
                try:
                    sc = silhouette_score(X, lbls, metric="cosine")
                except Exception:
                    continue
                # Штраф за сложность: предпочитаем меньше спикеров при близких sc
                sc_penalized = sc - 0.02 * (k - 2)
                if sc_penalized > best_sc:
                    best_sc, best_k = sc_penalized, k
            num_speakers = best_k
            log.info(f"Auto-detected {num_speakers} speakers (best penalized silhouette={best_sc:.3f})")
        else:
            num_speakers = max(1, min(num_speakers, n))
            if num_speakers == 1:
                return [{"start": s, "end": e, "speaker": 0} for s, e in windows]

        labels = AgglomerativeClustering(
            n_clusters=num_speakers, metric="cosine", linkage="average"
        ).fit_predict(X)

        # Гарантируем сортировку по start — assign_speaker зависит от этого
        segments = sorted(
            [{"start": s, "end": e, "speaker": int(lbl)}
             for (s, e), lbl in zip(windows, labels)],
            key=lambda x: x["start"],
        )
        return segments

    def _windows(self, duration: float) -> list[tuple[float, float]]:
        wins = []
        t = 0.0
        while t + self.chunk_duration <= duration:
            wins.append((t, t + self.chunk_duration))
            t += self.chunk_step
        if not wins or wins[-1][1] < duration:
            start = max(0.0, duration - self.chunk_duration)
            wins.append((start, duration))
        return wins
