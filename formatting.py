import json


def _srt_ts(s: float) -> str:
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"


def _txt_ts(s: float) -> str:
    m, s = divmod(s, 60)
    return f"{int(m):02}:{s:05.2f}"


def fmt_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def fmt_srt(utterances: list[dict]) -> str:
    lines = []
    for i, u in enumerate(utterances, 1):
        lines.append(
            f"{i}\n"
            f"{_srt_ts(u['start'])} --> {_srt_ts(u['end'])}\n"
            f"[{u['speaker_label']}] {u['text']}\n"
        )
    return "\n".join(lines)


def fmt_txt(utterances: list[dict]) -> str:
    lines, prev = [], None
    for u in utterances:
        lbl = u["speaker_label"]
        if lbl != prev:
            lines.append(f"\n{lbl} [{_txt_ts(u['start'])} → {_txt_ts(u['end'])}]")
            prev = lbl
        else:
            lines.append(f"  [{_txt_ts(u['start'])} → {_txt_ts(u['end'])}]")
        lines.append(f"  {u['text']}")
    return "\n".join(lines).strip()