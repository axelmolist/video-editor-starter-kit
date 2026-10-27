"""Captions for the engagement format.

Cue markup (in the episode config, host-audio time): {phrase} = accent emphasis (bigger), a leading "~" = the OTHER
person's line (muted blue-grey, slightly smaller). Never italic, never ALL CAPS.
"""
import os, re, sys
from . import timeline as TL
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from spelling import to_locale     # BLOCKING: every caption is in the configured spelling locale
import kitconfig
_P, _F = kitconfig.palette(), kitconfig.brand()["fonts"]

PLAYRES = (1080, 1920)
CAP_FONT = _F["captions"]["name"]
CAP_Y = 960                       # centre line of 1920 PlayRes == y 1920 at 4K == the split seam (BLOCKING: captions sit on the seam of the split layout)
FS, FS_EMPH, FS_OTHER = 70, 78, 64
# Shadow offset on the 1080x1920 PlayRes (+5/+10 read as too far from the text).
SHADOW_DX, SHADOW_DY = 2.5, 5
WHITE = r"\1c&H" + kitconfig.ass_bgr(_P["text"]) + "&"; ACCENT = r"\1c&H" + kitconfig.ass_bgr(_P["accent"]) + "&"; SHADOW = r"\1c&H0A0A0A&\1a&H47&"
OTHER = r"\1c&H" + kitconfig.ass_bgr(_P["muted"]) + "&"     # the other speaker, muted
POP = r"\fad(60,60)\fscx88\fscy88\t(0,120,\fscx100\fscy100)"
_EM = re.compile(r"\{(.+?)\}")


def ts(t): return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def secs(s):
    h, m, x = s.split(":"); return int(h) * 3600 + int(m) * 60 + float(x)


def styled(text, front):
    def r(mm):
        pre = rf"\fs{FS_EMPH}" + (ACCENT if front else "")
        post = rf"\fs{FS}" + (WHITE if front else "")
        return "{" + pre + "}" + mm.group(1) + "{" + post + "}"
    return _EM.sub(r, text)


HEADER = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n"
          "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
          "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
          "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
          "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
          f"Style: Cap,{CAP_FONT},{FS},&H00FAF6F3,&H00FFFFFF,&H00000000,&H00000000,"
          "0,0,0,0,100,100,0,0,1,0,0,5,108,108,0,1\n\n[Events]\n"
          "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def base_ass(cues, m, T, cap_y=CAP_Y):
    """The clean (full-frame) caption file: one cue per authored phrase, timed from the first spoken word (-50 ms) to
    the last (+450 ms, never into the next cue), 2 layers (blurred offset shadow + sharp text), fixed row cap_y."""
    cs = []
    for text, a, b in cues:
        text = to_locale(text)
        s, e = TL.to_out(m, a), TL.to_out(m, b)
        if s is None or e is None: raise SystemExit(f"cue outside segs: {text} {a} {b}")
        s = max(s - 0.05, 0.0)
        if e <= s: continue
        cs.append([text, s, e])
    cs.sort(key=lambda c: c[1])
    for i, c in enumerate(cs):
        nxt = cs[i + 1][1] if i + 1 < len(cs) else T - 0.02
        c[2] = min(c[2] + 0.45, nxt - 0.02, T - 0.02)
    ev = []
    for text, s, e in cs:
        if text.startswith("~"):
            text = text[1:]; back = front = text
            gs0, gs1 = rf"\fs{FS_OTHER}", rf"\fs{FS_OTHER}" + OTHER
        else:
            back, front = styled(text, False), styled(text, True); gs0 = gs1 = ""
        ev.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{{\\pos({540 + SHADOW_DX:g},{cap_y + SHADOW_DY:g})\\blur6{SHADOW}{POP}{gs0}}}" + back)
        ev.append(f"Dialogue: 1,{ts(s)},{ts(e)},Cap,,0,0,0,,{{\\pos(540,{cap_y}){POP}{gs1}}}" + front)
    leak = [l for l in ev if re.search(r"[{}]", re.sub(r"\{\\[^}]*\}", "", l.split(",,", 1)[1]))]
    if leak: raise SystemExit(f"markup leak: {leak[:2]}")
    return HEADER + "\n".join(ev) + "\n", len(cs)


def engagement_ass(base_text, pcs, T, suppress=(), fps=25):
    """Split every cue at each state boundary (so a cue spanning split -> full frame is two events at the SAME row; the
    continuation does not re-pop), and drop cue parts inside suppress windows (e.g. a full-screen quote card)."""
    head, ev = base_text.split("[Events]")
    lines = ev.strip().splitlines()
    fmt, dlg = lines[0], lines[1:]
    bounds = sorted(set([a / fps for a, b, k, sp in pcs] + [T]))
    out = []
    for L in dlg:
        pre, rest = L.split(": ", 1)
        parts = rest.split(",", 9)
        s, e = secs(parts[1]), secs(parts[2])
        cuts = [s] + [x for x in bounds if s < x < e] + [e]
        for i in range(len(cuts) - 1):
            a, b = cuts[i], cuts[i + 1]
            if b - a < 0.02: continue
            mid = (a + b) / 2
            if any(x0 <= mid < x1 for x0, x1 in suppress): continue
            txt = parts[9]
            if i > 0:
                txt = re.sub(r"\\fad\(\d+,\d+\)\\fscx88\\fscy88\\t\(0,120,\\fscx100\\fscy100\)", r"\\fad(0,60)", txt)
            p2 = parts[:]; p2[1] = ts(a); p2[2] = ts(b); p2[9] = txt
            out.append(f"{pre}: " + ",".join(p2))
    return head + "[Events]\n" + fmt + "\n" + "\n".join(out) + "\n"


def rows_fixed(ass_text, cap_y=CAP_Y):
    """gate: every front event at cap_y, every shadow event at cap_y + SHADOW_DY"""
    ys = re.findall(r"^Dialogue: (\d),.*?\\pos\([\d.]+,([\d.]+)\)", ass_text, re.M)
    front = sorted(set(float(y) for l, y in ys if l == "1")); back = sorted(set(float(y) for l, y in ys if l == "0"))
    return front == [cap_y] and back == [cap_y + SHADOW_DY], {"front": front, "shadow": back}
