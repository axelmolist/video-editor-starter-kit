"""CLEAN style shorts builder - one config per short, preview and 4K master from the same code.

Spec: video/instructions/formats/shorts/CLEAN-STYLE.md.

    python video/lib/clean_short.py <config.json>          # 720x1280 preview
    python video/lib/clean_short.py <config.json> --4k     # 2160x3840 master
    (needs numpy + Pillow, e.g. the video-use skill's venv; Chrome for the hook pill, CHROME=<path> to override)

Config (JSON, lives in the short's editor-files/; paths relative to that folder or absolute):
{
  "slug": "s6-example-short",
  "version": "v1",                         # bump on every preview; outputs are never overwritten
  "raw": "../../s6.mov",                   # or {"a": "../../s22-a.mov", "b": "../../s22-b.mov"} for a short split
                                           # across files; then "transcript" is a dict with the same keys and a
                                           # timeline sentence names its file: [12.3, 15.8, "b"] (default: first key)
  "transpose": 1,                          # ffmpeg transpose for sideways footage with no rotation tag, or null
  "transcript": "transcripts/s6.json",     # Scribe word-level JSON of the raw clip
  "anchor": [0.505, 0.495],                # chin position as a fraction of the upright frame (x, y)
  "base_zoom": 1.665,                      # optional: frame the speaker chest-up; wider camera set-ups need more (s5: 2.0)
  "hook": "The one number that matters",
  "hook_y": 230,                           # pill centre at 720x1280; clear of the head at the tightest punch-in
  "hook_px": 32,                           # optional: hook type size (default 32); a newline in "hook" breaks the line
  "timeline": [[40.34, 44.04], {"guest": "guest1", "in": 2256.68, "out": 2263.20}, [121.72, 125.24]],
                                           # [start, end] = one kept sentence/take (Scribe times); guests full screen
  "punch_at": [43.10, 132.08],             # punch in from this source time to the end of its segment
  "crossfade": 0.04,                       # optional: audio crossfade (s) at every join instead of 10 ms dips
  "punch_windows": [[2.4, 6.92]],          # optional: punched-in spans on the OUTPUT timeline (overrides punch_at);
                                           # hold every in and out state ~2 s (1.5-3 s), never flick in and out
  "cap_y": 770,                            # optional: caption centre y at 720x1280 (default 712)
  "splits": [{"t0": 0.0, "t1": 1.68, "video": "../broll/car.mp4", "grade": true}],
                                           # optional: split screen on the OUTPUT timeline - b-roll panel on top
                                           # (pre-rendered 2160x1920, 25 fps, from its first frame, blurs baked in),
                                           # host below with the chin at "split_chin" (0.75) of the lower half so the
                                           # captions sit in their headroom; "grade" = CLEAN grade for camera footage
                                           # "split_chin" (0.75) and "split_cap_y" (default cap_y) tune the host
                                           # framing and caption height inside split windows only
  "end_pill": {"text": "If that was useful, hit follow.", "dur": 2.0},   # optional: on-screen CTA replaces the
                                           # hook pill for the last dur seconds (when the CTA is not spoken)
  "punch_mode": "toggle",                  # optional: several punch times in one long take alternate in / out
                                           # (default: the first punch in a segment holds to its end)
  "numbers": {"thirty thousand": "30,000"},  # caption replacements (spoken words -> digits), optional
  "guests": {"guest1": {"video": "...mp4", "audio": "...webm", "transcript": "transcripts/guest1.json",
                     "transcript_offset": 2240.0, "scale_h": 1650, "track": "dark"}}   # optional: "track_top", "track_ignore_left";
                                           # "fit": "band" + "band_x": [0.165, 0.835] shows a slide/painting whole
                                           # as a centred band over a blurred fill of itself (s4)
}
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spelling import to_locale  # noqa: E402
import kitconfig  # noqa: E402

FPS = kitconfig.style()["output"]["fps"]
CHROME = __import__("os").environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CAP_FONT = kitconfig.brand()["fonts"]["captions"]["name"]
HOOK_FONT = kitconfig.brand()["fonts"]["title"]["name"]

# ---------------------------------------------------------------- the approved CLEAN look (all at 720x1280)
LEAD, TAIL = 0.02, 0.03          # silence kept before / after speech at every join
BASE_ZOOM, CREEP = 1.665, 0.066  # default framing (chest-up on the s6 camera) + creep as a fraction of it
PUNCH = 1.25                     # punch-in factor on top of the base
CAP_Y, CAP_SIZE, CAP_MAX = 712, 43, 18   # captions: just under the chin, caption font, <= 18 chars
HOOK_PX = 32                     # hook type size (white pill, black title font)
GRAIN = 0.014                    # mono grain std (0-1), drawn at 720x1280 so the grain size is resolution-independent
GRADE_LUT = np.interp(np.arange(256) / 255, [0, 0.15, 0.5, 0.75, 1.0], [0.02, 0.18, 0.51, 0.70, 0.90])
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
# a warm house grade (edit to taste, or let the colour-grader agent propose one): colour units -> offset at 0.004 per unit, luminance-preserving
TINT = {"shadows": np.array([0, 2, 6]), "mids": np.array([14, 0, 2]), "highs": np.array([19, 0, 1])}
TINT = {k: (v * 0.004 - (v * 0.004) @ LUMA).astype(np.float32) for k, v in TINT.items()}


def q_floor(t):
    return math.floor(t * FPS + 1e-6) / FPS


def q_ceil(t):
    return math.ceil(t * FPS - 1e-6) / FPS


def load_env(path, sr=16000):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32)
    win = sr // 100
    n = len(a) // win
    return 20 * np.log10(np.sqrt((a[: n * win].reshape(n, win) ** 2).mean(1)) + 1e-9)


def refine(env, start, end, thr=-55.0, run=8):
    """Walk out from the Scribe times to the true first/last sound (protects quiet onsets and tails)."""
    def silent_run_at(i, step):
        return all(0 <= i + k * step < len(env) and env[i + k * step] < thr for k in range(run))
    i = int(start * 100)
    lo = max(0, i - 60)
    while i > lo and not silent_run_at(i - 1, -1):
        i -= 1
    j = int(end * 100)
    hi = min(len(env) - 1, j + 60)
    while j < hi and not silent_run_at(j, +1):
        j += 1
    return i / 100, j / 100


def words(path, offset=0.0):
    d = json.loads(Path(path).read_text())
    return [(w["text"], w["start"] + offset, w["end"] + offset) for w in d["words"] if w.get("type") == "word"]


class Short:
    def __init__(self, cfg_path, master):
        self.cfg_path = Path(cfg_path).resolve()
        self.dir = self.cfg_path.parent
        self.c = json.loads(self.cfg_path.read_text())
        self.S = 3 if master else 1
        self.W, self.H = 720 * self.S, 1280 * self.S
        raws = self.c["raw"] if isinstance(self.c["raw"], dict) else {"a": self.c["raw"]}
        self.raws = {k: self.p(v) for k, v in raws.items()}
        self.key0 = next(iter(self.raws))
        tr = self.c["transcript"] if isinstance(self.c["transcript"], dict) else {self.key0: self.c["transcript"]}
        self.transcripts = {k: self.p(v) for k, v in tr.items()}
        self.raw = self.raws[self.key0]
        self.guests = {k: {**g, "video": self.p(g["video"]), "audio": self.p(g.get("audio", g["video"])),
                           "transcript": self.p(g["transcript"])} for k, g in self.c.get("guests", {}).items()}
        # upright source size; the preview pre-scales to 1800x3200 for speed, the master reads native
        pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "stream=width,height:stream_side_data=rotation", "-of", "json", str(self.raw)],
                                       capture_output=True, check=True).stdout)["streams"][0]
        w, h = pr["width"], pr["height"]
        rot = abs(int(next((d.get("rotation", 0) for d in pr.get("side_data_list", [])), 0)))
        if rot == 90:            # rotation-tagged clip: ffmpeg auto-rotates it upright (leave "transpose" null)
            w, h = h, w
        if self.c.get("transpose") is not None:
            w, h = h, w
        self.native = (w, h)
        self.src = (w, h) if master else (1800, 3200)
        self.anchor = (self.c["anchor"][0] * self.src[0], self.c["anchor"][1] * self.src[1])
        self.rng = np.random.default_rng(7)
        g = np.random.default_rng(1).normal(0, 1.0, (1280, 720)).astype(np.float32)
        self.grain_std = float(np.asarray(Image.fromarray(g, "F").resize((self.W, self.H), Image.BILINEAR)).std())
        final = self.dir.parent / "final-footage"
        final.mkdir(exist_ok=True)
        self.tag = "4k" if master else f"preview-720p-{self.c['version']}"
        self.out = final / f"{self.c['slug']}-{'4k' if master else 'preview-720p-' + self.c['version']}.mp4"
        self.work = self.dir / ("build-4k" if master else f"build-{self.c['version']}")
        self.work.mkdir(exist_ok=True)

    def p(self, x):
        x = Path(x)
        return x if x.is_absolute() else (self.dir / x).resolve()

    # ------------------------------------------------------------ cut list
    def cut_list(self):
        envs = {k: load_env(v) for k, v in self.raws.items()}
        segs = []
        for item in self.c["timeline"]:
            if isinstance(item, dict):
                segs.append({"kind": "guest", "guest": item["guest"], "in": q_floor(item["in"]), "out": q_ceil(item["out"])})
                continue
            src = item[2] if len(item) > 2 else self.key0
            # optional "silence_db": raise the floor (e.g. -44) to cut inhales between sentences too
            on, off = refine(envs[src], item[0], item[1], thr=self.c.get("silence_db", -55.0))
            segs.append({"kind": "host", "src": src, "in": q_floor(on - LEAD), "out": q_ceil(off + TAIL),
                         "onset": on, "offset": off})
        merged = []
        for s in segs:  # sentences whose padded windows touch become one segment: no cut
            if (merged and s["kind"] == merged[-1]["kind"] == "host" and s["src"] == merged[-1]["src"]
                    and merged[-1]["in"] <= s["in"] <= merged[-1]["out"]):   # forward only: a later take
                                                                              # from earlier in the file is a cut
                merged[-1]["out"] = max(merged[-1]["out"], s["out"])
                merged[-1]["offset"] = s["offset"]
            else:
                merged.append(dict(s))
        t = 0.0
        for s in merged:
            s["frames"] = round((s["out"] - s["in"]) * FPS)
            s["t0"] = t
            t += s["frames"] / FPS
        return merged, t

    # ------------------------------------------------------------ captions
    def captions(self, segs):
        host = {k: words(v) for k, v in self.transcripts.items()}
        gw = {k: words(g["transcript"], g.get("transcript_offset", 0.0)) for k, g in self.guests.items()}
        placed = []
        for s in segs:
            pool = gw[s["guest"]] if s["kind"] == "guest" else host[s["src"]]
            for txt, a, b in pool:
                # keep a word if its sound ends inside the segment; a start Scribe stretched back into the
                # silence before the cut is clamped to the cut (s11 "But" was dropped otherwise)
                if s["in"] < b <= s["out"] + 0.02 and a >= s["in"] - 1.0 and (a >= s["in"] - 0.02 or b - s["in"] > 0.08):
                    placed.append([txt, s["t0"] + max(a, s["in"]) - s["in"], s["t0"] + b - s["in"], s])
        numbers = {tuple(k.lower().split()): v for k, v in self.c.get("numbers", {}).items()}
        out, i = [], 0
        while i < len(placed):
            hit = None
            for key, val in numbers.items():
                n = len(key)
                run = placed[i:i + n]
                if (tuple(w[0].lower().strip(",.?!") for w in run) == key
                        and not any(w[0].endswith((".", "?", "!")) for w in run[:-1])):   # never across a sentence end
                    hit = (n, val)
                    break
            if hit:
                n, val = hit
                last = placed[i + n - 1][0]
                out.append([val + last[len(last.rstrip(",.?!")):], placed[i][1], placed[i + n - 1][2], placed[i][3]])
                i += n
            else:
                out.append(placed[i])
                i += 1
        phrases, cur = [], []
        for w in out:
            if cur and cur[-1][3] is not w[3]:
                phrases.append(cur)
                cur = []
            cur.append(w)
            w[0] = w[0].replace("--", "").rstrip("-") or w[0]   # stammer fragments ("was--", "ge-"): no dashes on screen
            if w[0].endswith((".", ",", "?", "!")):
                phrases.append(cur)
                cur = []
        if cur:
            phrases.append(cur)

        def width(ws):
            return len(" ".join(x[0] for x in ws).rstrip(",.?!"))

        def best_split(ws, k):
            # minimise the widest line; a one-word line (an orphan flash) costs 6 extra chars unless the
            # phrase is only one or two words, so balanced multi-word lines win
            if k == 1:
                return [ws], width(ws) + (6 if len(ws) == 1 and len(ph) > 2 else 0)
            best = (None, 1e9)
            for j in range(1, len(ws) - k + 2):
                rest, m = best_split(ws[j:], k - 1)
                sc = max(width(ws[:j]) + (6 if j == 1 and len(ph) > 2 else 0), m)
                if sc < best[1]:
                    best = ([ws[:j]] + rest, sc)
            return best

        chunks = []
        for ph in phrases:  # fewest one-line chunks of <= CAP_MAX chars, balanced (no orphans)
            k = 1
            while k < len(ph) and max(width(c) for c in best_split(ph, k)[0]) > CAP_MAX:
                k += 1
            chunks += best_split(ph, k)[0]
        res = []
        for n, ch in enumerate(chunks):
            text = to_locale(" ".join(x[0] for x in ch)).replace('"', "").replace("\u201c", "").replace("\u201d", "").rstrip(".,")
            seg_end = ch[-1][3]["t0"] + ch[-1][3]["frames"] / FPS
            nxt = chunks[n + 1][0][1] if n + 1 < len(chunks) else seg_end
            end = min(max(ch[-1][2] + 0.25, nxt if nxt - ch[-1][2] < 0.6 else ch[-1][2] + 0.25), seg_end, nxt)
            res.append((ch[0][1], end, text))
        return res

    def write_ass(self, chunks, path):
        S, W, H = self.S, self.W, self.H
        y = self.c.get("cap_y", CAP_Y) * S   # optional "cap_y": lower captions when the chin sits low

        def ts(t):
            cs = int(round(t * 100))
            return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"
        head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{CAP_FONT},{CAP_SIZE * S},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # optional "split_cap_y": caption centre during split windows (host in the lower half, raised with split_chin)
        sy = self.c.get("split_cap_y", self.c.get("cap_y", CAP_Y)) * S
        splits = [(sp["t0"], sp["t1"]) for sp in self.c.get("splits", [])]
        lines = []
        for a, b, t in chunks:
            y = sy if any(t0 <= (a + b) / 2 < t1 for t0, t1 in splits) else self.c.get("cap_y", CAP_Y) * S
            lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,"
                         f"{{\\pos({W // 2 + 2 * S},{y + 3 * S})\\1c&H1E1E1E&\\1a&H30&\\blur{5 * S}}}{t}")
            lines.append(f"Dialogue: 1,{ts(a)},{ts(b)},Cap,,0,0,0,,{{\\pos({W // 2},{y})}}{t}")
        path.write_text(head + "\n".join(lines) + "\n")

    def render_hook(self, path, text=None):
        text = text or self.c["hook"]
        html = f"""<html><body style="margin:0;background:transparent">
<div style="display:inline-block;margin:20px;padding:7px 17px 8px;border-radius:11px;background:#fff;
font:400 {self.c.get("hook_px", HOOK_PX)}px{"/1.18" if chr(10) in text else ""} '{HOOK_FONT}';color:#000;white-space:nowrap;text-align:center;
box-shadow:0 2px 7px rgba(0,0,0,.25)">{text.replace(chr(10), '<br>')}</div></body></html>"""
        with tempfile.TemporaryDirectory() as td:
            hp = Path(td) / "hook.html"
            hp.write_text(html)
            png = Path(td) / "hook.png"
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={td}/prof",
                            "--default-background-color=00000000", "--window-size=1600,220",
                            f"--force-device-scale-factor={2 * self.S}", f"--screenshot={png}", hp.as_uri()],
                           capture_output=True)
            if not png.exists():   # headless Chrome can exit non-zero after writing the shot: trust the file
                sys.exit("hook render failed: Chrome wrote no screenshot")
            im = Image.open(png).convert("RGBA")
            im = im.crop(im.getbbox())
            if im.width // 2 > 680 * self.S:   # wider than the frame minus a 20 px margin each side: refuse, don't clip
                sys.exit(f"hook pill is {im.width // 2 // self.S} px wide at 720 (max 680): shorten it, add a line break or set hook_px")
            im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)  # shot at 2x, kept at 1x per S
            im.save(path)
        return Image.open(path)

    # ------------------------------------------------------------ audio
    def build_audio(self, segs, path):
        # one seeked input per segment: takes can come from anywhere in a file, in any order (agencies: ask 2 sits
        # earlier in the file than ask 1), and a shared input stream would buffer, then drop, the earlier take
        xf = float(self.c.get("crossfade", 0)) if len(segs) > 1 else 0.0
        cmd, parts = ["ffmpeg", "-v", "error", "-y"], []
        for k, s in enumerate(segs):
            src = self.guests[s["guest"]]["audio"] if s["kind"] == "guest" else self.raws[s["src"]]
            dur = s["frames"] / FPS
            # optional "crossfade" (s): each join overlaps the two sides by this much, centred on the cut, so the
            # audio crossfades instead of dipping; every segment is extended by half of it per join to keep sync
            pre = xf / 2 if xf and k > 0 else 0.0
            post = xf / 2 if xf and k < len(segs) - 1 else 0.0
            cmd += ["-ss", f"{s['in'] - pre:.3f}", "-t", f"{dur + pre + post + 0.2:.3f}", "-i", str(src)]
            fade = "" if xf else f",afade=t=in:d=0.01,afade=t=out:st={dur - 0.01:.3f}:d=0.01"
            parts.append(f"[{k}:a]atrim=duration={dur + pre + post:.3f},asetpts=PTS-STARTPTS,"
                         f"aformat=sample_rates=48000:channel_layouts=mono{fade}[a{k}]")
        if xf:
            chain, prev = [], "[a0]"
            for k in range(1, len(segs)):
                chain.append(f"{prev}[a{k}]acrossfade=d={xf:.3f}:c1=tri:c2=tri[x{k}]")
                prev = f"[x{k}]"
            fc = ";".join(parts + chain) + f";{prev}loudnorm=I=-14:TP=-1.5:LRA=11[out]"
        else:
            fc = ";".join(parts) + ";" + "".join(f"[a{k}]" for k in range(len(segs))) + \
                 f"concat=n={len(segs)}:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[out]"
        subprocess.run(cmd + ["-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", str(path)], check=True)

    # ------------------------------------------------------------ video
    def host_reader(self, segs):
        # one seeked input per host segment (see build_audio): order-independent and no frame buffering
        ins, parts, labels = [], [], []
        for s in segs:
            if s["kind"] != "host":
                continue
            j = len(labels)
            ins += ["-ss", f"{s['in']:.3f}", "-i", str(self.raws[s["src"]])]
            parts.append(f"[{j}:v]trim=end_frame={s['frames']},setpts=PTS-STARTPTS[v{j}]")
            labels.append(f"[v{j}]")
        rot = f"transpose={self.c['transpose']}," if self.c.get("transpose") is not None else ""
        scale = "" if self.src == self.native else f"scale={self.src[0]}:{self.src[1]}:flags=lanczos,"
        fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=1:a=0,{rot}{scale}format=rgb24[out]"
        return subprocess.Popen(["ffmpeg", "-v", "error", *ins, "-filter_complex", fc, "-map", "[out]",
                                 "-f", "rawvideo", "-"], stdout=subprocess.PIPE)

    def guest_frames(self, seg):
        """Full-screen 9:16 crop of a 16:9 guest clip, scaled to scale_h (at 1280 high) so the caption line sits
        clear of their chest graphics, panning to follow them ("dark" = track a dark T-shirt, else centred)."""
        g = self.guests[seg["guest"]]
        dur = seg["frames"] / FPS
        if g.get("fit") == "band":
            return self.band_frames(g, seg)
        pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "stream=width,height", "-of", "json", str(g["video"])],
                                       capture_output=True, check=True).stdout)["streams"][0]
        nw, nh = pr["width"], pr["height"]
        fh = g.get("scale_h", 1280)
        fw = int(round(nw * fh / nh / 2)) * 2
        if g.get("track") == "dark":
            cmd = ["ffmpeg", "-v", "error", "-ss", f"{seg['in']:.3f}", "-i", str(g["video"]), "-t", f"{dur + 0.2:.3f}",
                   "-vf", f"fps=25,scale={fw}:{fh}:flags=lanczos,crop={fw}:1280:0:0,format=rgb24",
                   "-frames:v", str(seg["frames"]), "-f", "rawvideo", "-"]
            raw = subprocess.run(cmd, capture_output=True, check=True).stdout
            sz = fw * 1280 * 3
            xs = []
            for i in range(0, len(raw) - sz + 1, sz):
                f = np.frombuffer(raw[i:i + sz], np.uint8).reshape(1280, fw, 3)
                # black T-shirt only (dark stage edges can pull the centroid); optional per-clip limits for a
                # dark set piece in shot (s7: track_top 900 = lower torso, track_ignore_left 0.12 = stage curve)
                sub = f[g.get("track_top", 380):1280:4, ::4]
                # "track_metric": "sum" = the s3/s6/s7 v1 test (R+G+B < 110); default "max" = s5 (every channel < 45)
                dark = sub.astype(np.int16).sum(2) < 110 if g.get("track_metric") == "sum" else sub.max(2) < 45
                col = dark.sum(0)
                col[: int(g.get("track_ignore_left", 0) * len(col))] = 0
                xs.append((col * np.arange(len(col))).sum() / col.sum() * 4 if col.sum() > 50 else (xs[-1] if xs else fw / 2))
            del raw
            xs = (xs or [fw / 2]) + [xs[-1] if xs else fw / 2] * max(0, seg["frames"] - len(xs))
            k = g.get("track_smooth", 15)   # pan smoothing half-window in frames (s5 v1: 6)
            sm = np.convolve(np.pad(np.array(xs), k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
        else:
            sm = np.full(seg["frames"], fw * g.get("centre_x", 0.5))
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{seg['in']:.3f}", "-i", str(g["video"]), "-t", f"{dur + 0.2:.3f}",
               "-vf", "fps=25,format=rgb24", "-frames:v", str(seg["frames"]), "-f", "rawvideo", "-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        nsz = nw * nh * 3
        nat = [raw[i:i + nsz] for i in range(0, len(raw) - nsz + 1, nsz)]
        nat += [nat[-1]] * max(0, seg["frames"] - len(nat))
        sc = fh / nh
        out = []
        for buf, cx in zip(nat, sm):
            x0 = int(min(max(cx - 360, 0), fw - 720))
            im = Image.frombuffer("RGB", (nw, nh), buf)
            out.append(np.asarray(im.resize((self.W, self.H), Image.LANCZOS, box=(x0 / sc, 0, (x0 + 720) / sc, 1280 / sc))))
        return out

    def band_frames(self, g, seg):
        """A slide or painting shown whole: centred band over a blurred, darkened fill of itself, slow push (s4)."""
        from PIL import ImageEnhance, ImageFilter
        W, H, S = self.W, self.H, self.S
        dur = seg["frames"] / FPS
        pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                        "stream=width,height", "-of", "json", str(g["video"])],
                                       capture_output=True, check=True).stdout)["streams"][0]
        nw, nh = pr["width"], pr["height"]
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seg['in']:.3f}", "-i", str(g["video"]), "-t",
                              f"{dur + 0.2:.3f}", "-vf", "fps=25,format=rgb24", "-frames:v", str(seg["frames"]),
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        sz = nw * nh * 3
        fr = [Image.frombuffer("RGB", (nw, nh), raw[i:i + sz]) for i in range(0, len(raw) - sz + 1, sz)]
        fr += [fr[-1]] * max(0, seg["frames"] - len(fr))
        x0, x1 = (int(f * nw) for f in g.get("band_x", [0.0, 1.0]))
        bwid = x1 - x0
        out = []
        for k, f in enumerate(fr):
            bg = f.resize((W, H), Image.BICUBIC, box=(bwid / 2 + x0 - bwid * 0.32, 0, bwid / 2 + x0 + bwid * 0.32, nh))
            bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(28 * S))).enhance(0.55)
            z = 1.0 + 0.04 * k / max(1, seg["frames"] - 1)
            bw, bh = bwid / z, nh / z
            cx, cy = (x0 + x1) / 2, nh / 2
            band_h = round(W * nh / bwid)
            bg.paste(f.resize((W, band_h), Image.LANCZOS, box=(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)),
                     (0, (H - band_h) // 2))
            out.append(np.asarray(bg))
        return out

    @staticmethod
    def grade(img):
        x = GRADE_LUT[np.asarray(img)].astype(np.float32)
        y = x @ LUMA
        ws = np.clip(1 - y / 0.4, 0, 1)[..., None]
        wh = np.clip((y - 0.55) / 0.45, 0, 1)[..., None]
        wm = np.clip(1 - ws - wh, 0, 1)
        x = x + ws * TINT["shadows"] + wm * TINT["mids"] + wh * TINT["highs"]
        y = (x @ LUMA)[..., None]
        return y + (x - y) * (1 + 0.2 * ws + 0.1 * wm)   # shadow saturation 1.2, mids 1.1

    def finish(self, x):
        g = self.rng.normal(0, 1.0, (1280, 720)).astype(np.float32)
        if self.S != 1:
            g = np.asarray(Image.fromarray(g, "F").resize((self.W, self.H), Image.BILINEAR), np.float32) / self.grain_std
        return Image.fromarray((np.clip(x + (g * GRAIN)[..., None], 0, 1) * 255 + 0.5).astype(np.uint8))

    def split_frames(self, sp):
        """Top-half panel frames for one split window, read at output size (2160x1920 source)."""
        n = round((sp["t1"] - sp["t0"]) * FPS)
        w, h = self.W, self.H // 2
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.p(sp["video"])), "-vf",
                              f"fps={FPS},scale={w}:{h}:flags=lanczos,format=rgb24", "-frames:v", str(n),
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        fr = [raw[i:i + w * h * 3] for i in range(0, len(raw) - w * h * 3 + 1, w * h * 3)]
        if len(fr) < n:
            print(f"  split {sp['t0']:.2f}: panel has {len(fr)} of {n} frames, holding the last")
        fr += [fr[-1]] * (n - len(fr))
        return [Image.frombuffer("RGB", (w, h), b) for b in fr]

    def crop_half(self, img, bw, bh):
        """Lower-half host framing for a split: same scale as the full frame, chin at split_chin of the half."""
        cx, cy = self.anchor
        hh = bh / 2
        x0 = min(max(cx - bw / 2, 0), self.src[0] - bw)
        y0 = min(max(cy - self.c.get("split_chin", 0.75) * hh, 0), self.src[1] - hh)
        return img.resize((self.W, self.H // 2), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + hh))

    def crop_resize(self, img, bw, bh):
        cx, cy = self.anchor
        x0 = min(max(cx - bw / 2, 0), self.src[0] - bw)
        y0 = min(max(cy - bh / 2, 0), self.src[1] - bh)
        return img.resize((self.W, self.H), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))

    def build(self, force=False):
        if self.out.exists() and not force:
            sys.exit(f"{self.out.name} exists - bump 'version' in the config (never overwrite a render)")
        segs, total = self.cut_list()
        (self.work / "cut_list.json").write_text(json.dumps(segs, indent=2))
        for s in segs:
            print(f"{s.get('guest', 'host'):5s} src {s['in']:8.2f}-{s['out']:8.2f}  out {s['t0']:6.2f}  ({s['frames'] / FPS:.2f}s)")
        print(f"total {total:.2f}s")
        ass = self.work / "captions.ass"
        self.write_ass(self.captions(segs), ass)
        hook = self.render_hook(self.work / "hook.png")
        audio = self.work / "audio.wav"
        self.build_audio(segs, audio)
        shutil.copy(self.cfg_path, self.work / "config.json")      # exact recipe of this render

        crf = ["-preset", "slow", "-crf", "18", "-profile:v", "high"] if self.S == 3 else ["-preset", "medium", "-crf", "19"]
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{self.W}x{self.H}",
                                "-r", str(FPS), "-i", "-", "-i", str(audio), "-vf", f"subtitles={ass}",
                                "-c:v", "libx264", *crf, "-pix_fmt", "yuv420p", "-r", str(FPS),
                                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(self.out)],
                               stdin=subprocess.PIPE)
        reader = self.host_reader(segs)
        fsize = self.src[0] * self.src[1] * 3
        hook_pos = ((self.W - hook.width) // 2, self.c["hook_y"] * self.S - hook.height // 2)
        # optional "end_pill": {"text": "If that was useful, hit follow.", "dur": 2.0} - the hook pill swaps to the
        # on-screen CTA for the last dur seconds (used when the CTA is not spoken in the source)
        endp = self.c.get("end_pill")
        if endp:
            end_img = self.render_hook(self.work / "end_pill.png", endp["text"])
            end_pos = ((self.W - end_img.width) // 2, self.c["hook_y"] * self.S - end_img.height // 2)
            end_n = round((total - endp.get("dur", 2.0)) * FPS)
        punches = self.c.get("punch_at", [])
        splits = self.c.get("splits", [])
        panels = {}
        n = 0
        for s in segs:
            gframes = self.guest_frames(s) if s["kind"] == "guest" else None
            inside = sorted(p for p in punches if s["kind"] == "host" and s["in"] <= p < s["out"])
            toggle = self.c.get("punch_mode") == "toggle"
            for f in range(s["frames"]):
                t = n / FPS
                if gframes is not None:
                    canvas = self.finish(gframes[f].astype(np.float32) / 255)   # guest: no grade, grain only, no hook
                else:
                    src = Image.frombuffer("RGB", self.src, reader.stdout.read(fsize))
                    bz = self.c.get("base_zoom", BASE_ZOOM)   # wider camera set-ups need more (s5: 2.0)
                    st = s["in"] + f / FPS
                    passed = sum(p <= st for p in inside)
                    punched = (passed % 2 == 1) if toggle else passed > 0
                    if "punch_windows" in self.c:   # optional: [[t0, t1], ...] in OUTPUT seconds, overrides punch_at
                        punched = any(a <= t < b for a, b in self.c["punch_windows"])
                    sp = next((x for x in splits if round(x["t0"] * FPS) <= n < round(x["t1"] * FPS)), None)
                    if sp is not None:   # split screen: panel on top, host below at the unpunched scale
                        k = splits.index(sp)
                        if k not in panels:
                            panels = {k: self.split_frames(sp)}   # one window in memory at a time
                        top = panels[k][min(n - round(sp["t0"] * FPS), len(panels[k]) - 1)]
                        top = self.grade(top) if sp.get("grade") else np.asarray(top, np.float32) / 255
                        z = bz * (1 + CREEP * t / total)
                        bot = self.grade(self.crop_half(src, self.src[0] / z, self.src[1] / z))
                        canvas = self.finish(np.concatenate([top, bot], 0))
                    else:
                        z = bz * (1 + CREEP * t / total) * (PUNCH if punched else 1.0)
                        canvas = self.finish(self.grade(self.crop_resize(src, self.src[0] / z, self.src[1] / z)))
                    if endp and n >= end_n:
                        canvas.paste(end_img, end_pos, end_img)
                    else:
                        canvas.paste(hook, hook_pos, hook)
                enc.stdin.write(canvas.tobytes())
                n += 1
        enc.stdin.close()
        enc.wait()
        reader.wait()
        print("wrote", self.out)
        self.qc(segs, total)

    def qc(self, segs, total):
        """Contact sheet (with the last frame of every punched segment = tightest framing) + join audit."""
        a = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(self.out), "-ac", "1", "-ar", "16000",
                                          "-f", "f32le", "-"], capture_output=True, check=True).stdout, np.float32)

        def lv(t0, t1):
            x = a[int(t0 * 16000):int(t1 * 16000)]
            return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) if len(x) else -99
        speech = np.percentile([lv(t, t + 0.5) for t in np.arange(0, total - 0.5, 0.5)], 75)
        print(f"QC join audit (speech ~{speech:.0f} dB; a join edge should be >= 25 dB quieter):")
        bad = 0
        for s in segs:
            t0, t1 = s["t0"], s["t0"] + s["frames"] / FPS
            h, tl = lv(t0, t0 + 0.02), lv(t1 - 0.02, t1)
            flag = "" if max(h, tl) < speech - 25 else "  <-- CHECK"
            bad += bool(flag)
            print(f"  {s.get('guest', s.get('src')):5s} {t0:6.2f}-{t1:6.2f} head {h:6.1f} tail {tl:6.1f}{flag}")
        times = list(np.linspace(0.5, total - 0.2, 8))
        for s in segs:
            if s["kind"] == "host" and any(s["in"] <= p < s["out"] for p in self.c.get("punch_at", [])):
                times.append(s["t0"] + s["frames"] / FPS - 0.1)
        times = sorted(times)
        times = [times[round(i)] for i in np.linspace(0, len(times) - 1, min(15, len(times)))]   # whole short, not the first 15
        sheet = self.out.with_name(self.out.stem + "-contact.jpg")
        sel = "+".join(f"eq(n\\,{int(t * FPS)})" for t in times)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.out), "-vf",
                        f"select='{sel}',scale=240:-1,tile=5x{math.ceil(len(times) / 5)}", "-frames:v", "1",
                        str(sheet)], check=True)
        print(f"QC contact sheet: {sheet} (check: hook clears the hair on punched frames, captions readable)")
        print("QC joins:", "OK" if not bad else f"{bad} segment(s) to check by ear")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--4k", dest="master", action="store_true", help="render the 2160x3840 master (after approval)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing render (only when the creator asks)")
    a = ap.parse_args()
    Short(a.config, a.master).build(a.force)
