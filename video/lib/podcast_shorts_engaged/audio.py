"""Programme audio for one short.

Host mic (always open) + the other person's mic gated open only inside their reply windows (30 ms ramps, a per-window
gain as an optional 3rd value), cut per the frame-snapped segments with 10/20/45 ms edge fades, light bus compression +
limiter, then two-pass linear loudnorm to -14 LUFS / -1.5 dBTP. The voice is never otherwise changed; no SFX bed in
this format. plan() only builds the commands; run() executes them (audio files are allowed without export approval).
"""
import json, subprocess


def gate_expr(windows, seekA, default_gain=1.0, ramp=0.03):
    if not windows: return "0"
    parts = []
    for w in windows:
        w0, w1 = w[0], w[1]; g = w[2] if len(w) > 2 else default_gain
        r0, r1 = w0 - seekA, w1 - seekA
        parts.append(f"{g:.3f}*clip((t-{r0 - ramp:.3f})/{ramp:g}\\,0\\,1)*clip(({r1 + ramp:.3f}-t)/{ramp:g}\\,0\\,1)")
    return "+".join(parts)


def plan(S, m, fps, host_wav, other_wav, raw_out):
    seekA = min(x[0] for x in m) - 2.0          # min/max: segments may be out of source order (remote-build lifted hooks);
    span = max(x[1] for x in m) - seekA + 2.0   # identical to m[0]/m[-1] for in-order cuts
    fc = [f"[1:a]asetnsamples=n=96,volume='{gate_expr(S.get('other_mic_windows', []), seekA, S.get('other_mic_gain', 1.0))}':eval=frame[g]",
          ("[0:a]asetnsamples=n=96,volume='1-(" + gate_expr([list(w[:2]) + [1.0] for w in S["owner_mic_mute_windows"]], seekA) + ")':eval=frame[h]"
           if S.get("owner_mic_mute_windows") else "[0:a]anull[h]")]   # optional: mute the open mic where the other
                                                                        # person talks over a backchannel (remote-build)
    k = len(m)
    fc.append(f"[h]asplit={k}" + "".join(f"[h{i}]" for i in range(k)))
    fc.append(f"[g]asplit={k}" + "".join(f"[g{i}]" for i in range(k)))
    for i, (a0, a1, n, t0) in enumerate(m):
        r0, r1 = a0 - seekA, a0 - seekA + n / fps
        dur = n / fps
        fin = 0.010 if i == 0 else 0.020
        fst = max(0.0, S["head_in"] - a0) if (i == 0 and "head_in" in S) else 0.0
        fout = 0.045 if i == k - 1 else 0.020
        for src in ("h", "g"):
            fc.append(f"[{src}{i}]atrim=start={r0:.5f}:end={r1:.5f},asetpts=PTS-STARTPTS[{src}t{i}]")
        fc.append(f"[ht{i}][gt{i}]amix=inputs=2:normalize=0,afade=t=in:st={fst:.4f}:d={fin},"
                  f"afade=t=out:st={dur - fout:.4f}:d={fout}[s{i}]")
    fc.append("".join(f"[s{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1,aformat=sample_rates=48000:channel_layouts=mono,"
              "acompressor=threshold=0.063:ratio=2.5:attack=8:release=150:makeup=2,"
              "alimiter=limit=0.35:attack=3:release=60:level=false[mix]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{seekA:.4f}", "-t", f"{span:.3f}", "-i", host_wav,
           "-ss", f"{seekA:.4f}", "-t", f"{span:.3f}", "-i", other_wav,
           "-filter_complex", ";".join(fc), "-map", "[mix]", "-c:a", "pcm_s24le", raw_out]
    return cmd


def _measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    import re
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1]), float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)[-1])


def finalise(path, lufs=-14, tp=-1.5, tries=4):
    """True-peak-safe landing (remote-build,: linear loudnorm alone came out about -15.5 LUFS with true peaks up to
    -0.2 dBTP. Gain to the target, then a limiter run at 4x oversampling (so it catches inter-sample peaks) with 1 dB of
    headroom under the TP target; re-measure and repeat until I is within 0.3 LU and TP <= target. Level only: the voice
    is not otherwise changed."""
    import os, shutil
    tmp = path + ".fin.wav"; lim = 10 ** ((tp - 1.0) / 20)
    for _ in range(tries):
        I, P = _measure(path)
        if abs(I - lufs) <= 0.3 and P <= tp: return I, P
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-af",
                        f"volume={lufs - I + (0.25 if I < lufs else 0):.2f}dB,aresample=192000,alimiter=limit={lim:.4f}:attack=1:release=60:level=false,aresample=48000",
                        "-c:a", "pcm_s24le", tmp], check=True)
        shutil.move(tmp, path)
    return _measure(path)


def run(cmd, raw_out, final_out, lufs=-14, tp=-1.5):
    subprocess.run(cmd, check=True)
    p = subprocess.run(["ffmpeg", "-v", "info", "-i", raw_out, "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    js = json.loads(p.stderr[p.stderr.rfind("{"):p.stderr.rfind("}") + 1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw_out, "-af",
                    f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
                    f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,"
                    "aresample=48000", "-c:a", "pcm_s24le", final_out], check=True)
    finalise(final_out, lufs, tp)
    return final_out
