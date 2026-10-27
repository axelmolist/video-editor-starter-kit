#!/usr/bin/env python3
"""Podcast-shorts ENGAGEMENT format - per-episode driver.
Spec (read first): video/instructions/formats/podcasts/PODCAST-SHORTS-ENGAGEMENT-FORMAT.md

  cli.py <episode.json> words <slug>              kept words in output time, both speakers (author cues/states from it)
  cli.py <episode.json> plan <slug|all>           NO VIDEO: captions (clean + engagement), hook card, filter graphs for
                                                  both camera layers and both compositors, change log, pre-render gates
  cli.py <episode.json> audio <slug|all>          audio_final.wav (audio files are allowed without export approval)
  cli.py <episode.json> render <stage> <slug> --approved-export
                                                  stage = layers | review | preview | engagement | clean. Video files: ONLY after
                                                  the creator's explicit go-ahead (AGENTS.md "Video export approval")
  cli.py <episode.json> verify <slug>             render gates on the delivered files
Options: --shorts-root <dir> writes everything under <dir> instead of the episode's shorts/ folder (dry runs).
Run with a Python that has numpy + PIL (e.g. the video-use skill's venv), from anywhere.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from podcast_shorts_engaged import audio as AU, captions as CAP, compose as CO, gates as GA, hook as HK, layers as LY, timeline as TL
from podcast_shorts_engaged.config import Episode
from spelling import to_locale, find_off_locale     # BLOCKING: British English everywhere
import caption_dedupe as CD     # BLOCKING: no animation text that duplicates the captions on screen


def anim_texts(S):
    """On-screen animation text for the caption-dedupe gate, OUTPUT time: [{id, start, end, text}].
    Declared: the short's "anim_texts" (authoritative - every label/word the top animation shows, with its window).
    Fallback (unverified): the 'quoted' labels inside each review_beats[].what_it_shows, over the beat's window."""
    if S.get("anim_texts") is not None:      # an empty declared list = the animation shows no text at all (remote-build wrong-metric)
        return S["anim_texts"], "declared"
    out = []
    for b in S.get("review_beats", []):
        for q in re.findall(r"'([^']{1,60})'", b.get("what_it_shows", "")):
            out.append({"id": b.get("id"), "start": b["start"], "end": b["end"], "text": q})
    return out, "derived-from-review_beats (UNVERIFIED: declare anim_texts)"


def dedupe(ep, slug):
    """caption-dedupe gate on the engagement caption file (suppress windows already applied) -> (ok, report)."""
    S = ep.short(slug); p = os.path.join(ep.altdir(slug), "caps_alt.ass")
    if not os.path.exists(p): return None, {"note": "caps_alt.ass missing - run plan first"}
    anims, src = anim_texts(S)
    ov = CD.find_overlaps(CD.load_captions(p), anims)
    return not ov, {"source": src, "anim_texts": len(anims), "overlaps": ov}


def words(ep, slug):
    S = ep.short(slug); m, T = ep.seg_map(slug)
    if ep.c.get("adapter") == "face4k":     # face4k-build: owner/other by the short's owner, per-mic attributed transcripts
        from podcast_shorts_engaged import face4k as F4; return F4.words(ep, slug)
    if ep.multicam:     # attributed words (owner: forced alignment; listeners: bleed-corrected mic energy), mic time
        print(f"[{slug}] total {T:.2f}s")
        for a, b, who, w in json.load(open(ep.p(ep.c["audio"]["word_source"])))[slug]:
            for a0, a1, n, t0 in m:
                if a0 - 0.05 <= a < a1: print(f"{t0 + max(a, a0) - a0:6.2f}  {a:8.2f}  {who:5s} {to_locale(w)}")
        return
    _, own_tr, _, oth_tr = ep.mics(slug)      # the short's OWNER is the open mic ("HOST" column = owner)
    hw = [w for w in json.load(open(own_tr))["words"] if w.get("type") == "word"]
    gw = [w for w in json.load(open(oth_tr))["words"] if w.get("type") == "word"]
    rows = [("HOST", w) for w in hw] + [("OTHER", w) for w in gw if any(x[0] <= w["start"] <= x[1] for x in S.get("other_mic_windows", []))]
    rows.sort(key=lambda r: r[1]["start"])
    print(f"[{slug}] total {T:.2f}s")
    for who, w in rows:
        for a0, a1, n, t0 in m:
            if a0 <= w["start"] < a1: print(f"{t0 + w['start'] - a0:6.2f}  {w['start']:8.2f}  {who:5s} {to_locale(w['text'])}")


def plan(ep, slug, seek_cache=None):
    S = ep.short(slug); fps = ep.fps
    m, T = ep.seg_map(slug)
    os.makedirs(ep.altdir(slug), exist_ok=True); os.makedirs(ep.final_dir(slug), exist_ok=True)
    rep = {"slug": slug, "duration": round(T, 2)}
    # captions
    base, n = CAP.base_ass(S["cues"], m, T)
    p_clean = os.path.join(ep.edir(slug), "caps_v6.ass"); open(p_clean, "w").write(base)
    E = S["engagement"]; pcs, TF = TL.state_pieces(E["states"], E["T"], fps)
    eng = CAP.engagement_ass(base, pcs, E["T"], E.get("suppress", []), fps)
    p_eng = os.path.join(ep.altdir(slug), "caps_alt.ass"); open(p_eng, "w").write(eng)
    rep["captions_fixed_centre"] = CAP.rows_fixed(base)[0] and CAP.rows_fixed(eng)[0]
    # hook
    hcfg = ep.c.get("hook", {})
    card_fn = HK.card
    if hcfg.get("renderer") == "chrome":     # opt-in: Chrome-typeset (kerned) card, same geometry; multicam-build (PIL looked "collaged")
        from podcast_shorts_engaged import hook_chrome as HKC; card_fn = HKC.card
    rep["hook_american_spellings"] = find_off_locale(S["title"][0])     # gate: must be [] (card renders to_locale)
    hk = card_fn(to_locale(S["title"][0]), os.path.join(ep.edir(slug), "title_4k.png"), hcfg.get("scale", HK.HOOK_SCALE),
                 hcfg.get("prefer_accent_break", True))
    rep["hook"] = {k: hk[k] for k in ("line_text", "font_px_4k", "card_bottom_4k", "card_w_1080")}
    # camera layers (graphs + records only)
    recs = {}
    for layout in ("full", "panel"):
        fc, cmd, rec, fpath = LY.plan(ep, slug, layout, hk["bottom"], seek_cache)
        open(fpath, "w").write(";\n".join(fc)); json.dump(rec, open(os.path.join(ep.altdir(slug), f"base_{layout}.json"), "w"), indent=1)
        json.dump(cmd, open(fpath.replace(".txt", ".cmd.json"), "w")); recs[layout] = rec
    # compositors
    fc, cmd, edl, fpath = CO.plan_engagement(ep, slug, p_eng, recs["full"], hook_bottom=hk["bottom"])
    open(fpath, "w").write(";\n".join(fc)); json.dump(cmd, open(fpath.replace(".txt", ".cmd.json"), "w"))
    json.dump(edl, open(os.path.join(ep.altdir(slug), "alt_edl.json"), "w"), indent=1)
    fc2, cmd2, fpath2 = CO.plan_clean(ep, slug, p_clean, T, recs["full"], hk["bottom"])
    open(fpath2, "w").write(";\n".join(fc2)); json.dump(cmd2, open(fpath2.replace(".txt", ".cmd.json"), "w"))
    # pre-render gates
    rep["engagement_T_matches_edit"] = abs(E["T"] - T) < 0.021
    rep["max_change_gap"] = edl["max_gap"]; rep["gap_le_2s"] = edl["max_gap"][0] <= 2.0
    cp = os.path.join(ep.edir(slug), "clean_punch.json")
    clean_pcs = json.load(open(cp)) if (ep.short(slug).get("clean_punch") and os.path.exists(cp)) else []
    ok, hh = GA.hook_hair(ep, recs["full"], edl["pieces"] + clean_pcs, hk["bottom"]); rep["hook_clears_hair"] = ok; rep["hair_rows"] = hh
    rep["punch_ins"] = [{k: p[k] for k in ("t0", "t1", "z", "z_requested", "pivot_y", "hair_clearance_punch") if k in p}
                        for p in edl["pieces"] if p.get("z", 1.0) != 1.0 or "z_requested" in p]
    ok, dd = dedupe(ep, slug); rep["caption_anim_dedupe_ok"] = ok; rep["caption_anim_dedupe"] = dd
    rep["bottom_covered_by_picture"] = all(x["crop_bottom_max" if "crop_bottom_max" in x else "crop_bottom"] <= x["source_bottom"] + 0.5
                                           for x in recs["full"]["framing"])
    return rep


def main():
    a = sys.argv[1:]
    root = None
    if "--shorts-root" in a:
        i = a.index("--shorts-root"); root = a[i + 1]; del a[i:i + 2]
    approved = "--approved-export" in a
    a = [x for x in a if x != "--approved-export"]
    ep = Episode(a[0], root); cmd = a[1]
    if cmd == "words": return words(ep, a[2])
    if cmd == "render":
        stage, slug = a[2], a[3]
        if not approved: raise SystemExit("REFUSED: rendering video needs the creator's explicit export go-ahead (AGENTS.md). Re-run with --approved-export once they have said so.")
        if stage in ("engagement", "review", "preview"):     # caption-dedupe pre-render gate
            ok, dd = dedupe(ep, slug)
            if ok is False:
                print(CD.format_overlaps(dd["overlaps"]))
                if dd["source"] == "declared":
                    raise SystemExit(f"REFUSED [{slug}]: animation text duplicates the captions on screen (above). Rewrite/remove the "
                                     "animation's text, or - if the text IS the beat - add a suppress window. Then re-plan.")
                print(f"WARNING [{slug}]: possible caption/animation duplicates from review_beats labels (unverified). Declare "
                      "the short's anim_texts so this gate can block for real.")
            elif ok and dd["source"] != "declared":
                print(f"WARNING [{slug}]: caption-dedupe ran on labels derived from review_beats - declare anim_texts.")
        if stage == "layers":
            for layout in ("full", "panel"):
                f = os.path.join(ep.altdir(slug), f"filter_base_{layout}.cmd.json"); subprocess.run(json.load(open(f)), check=True)
        else:
            name = {"engagement": "filter_alt.cmd.json", "clean": "../filter_v6.cmd.json"}.get(stage)
            if stage == "review":     # low-res review file in the short's folder (remote-build): <slug>-REVIEW-lowres.mp4, 720x1280
                rec = json.load(open(os.path.join(ep.altdir(slug), "base_full.json")))
                hb = HK.bottom(to_locale(ep.short(slug)["title"][0]), ep.c.get("hook", {}).get("scale", HK.HOOK_SCALE), ep.c.get("hook", {}).get("prefer_accent_break", True))
                out = os.path.join(ep.shorts_dir, slug, f"{slug}-REVIEW-lowres.mp4")
                fc, c, _, fpath = CO.plan_engagement(ep, slug, os.path.join(ep.altdir(slug), "caps_alt.ass"), rec, hook_bottom=hb, review_out=out)
                open(fpath, "w").write(";\n".join(fc)); return subprocess.run(c, check=True)
            if stage == "preview":
                rec = json.load(open(os.path.join(ep.altdir(slug), "base_full.json")))
                prev = os.path.join(ep.shorts_dir, "_review", "tmp"); os.makedirs(prev, exist_ok=True)
                hb = HK.bottom(to_locale(ep.short(slug)["title"][0]), ep.c.get("hook", {}).get("scale", HK.HOOK_SCALE), ep.c.get("hook", {}).get("prefer_accent_break", True))
                fc, c, _, fpath = CO.plan_engagement(ep, slug, os.path.join(ep.altdir(slug), "caps_alt.ass"), rec, preview_dir=prev, hook_bottom=hb)
                open(fpath, "w").write(";\n".join(fc)); return subprocess.run(c, check=True)
            subprocess.run(json.load(open(os.path.normpath(os.path.join(ep.altdir(slug), name)))), check=True)
        return
    slugs = ep.slugs() if a[2] == "all" else [a[2]]
    for slug in slugs:
        if cmd == "plan": print(json.dumps(plan(ep, slug), indent=1))
        elif cmd == "audio":
            S = ep.short(slug); m, T = ep.seg_map(slug)
            raw = os.path.join(ep.edir(slug), "audio_mix_raw.wav"); fin = os.path.join(ep.edir(slug), "audio_final.wav")
            if ep.c.get("adapter") == "face4k":
                from podcast_shorts_engaged import face4k as F4; c = F4.plan_audio(ep, slug, raw)
            elif ep.multicam:
                from podcast_shorts_engaged import multicam as MC; c = MC.plan_audio(ep, slug, raw)
            else:
                own_wav, _, oth_wav, _ = ep.mics(slug)     # owner mic open, the other gated (host-owned: unchanged)
                c = AU.plan(S, m, ep.fps, own_wav, oth_wav, raw)
            AU.run(c, raw, fin, ep.c["audio"].get("loudness_lufs", -14), ep.c["audio"].get("true_peak", -1.5)); print(fin)
        elif cmd == "verify":
            out = {}; sync_cache = {}
            pcs, _ = TL.state_pieces(ep.short(slug)["engagement"]["states"], ep.short(slug)["engagement"]["T"], ep.fps)
            for name, path, topf in (("engagement", os.path.join(ep.final_dir(slug), f"{slug}-ALT-engagement.mp4"),
                                      {f for a0, b0, k, sp in pcs if k != "S" for f in range(a0, b0)}),
                                     ("clean", os.path.join(ep.final_dir(slug), f"{slug}.mp4"), None)):
                if not os.path.exists(path): continue
                r = {}
                r["1_timestamps"] = GA.timestamps(path); r["2_no_dup_runs"] = GA.dup_runs(path); r["3_decode"] = GA.decode_clean(path)
                rec = json.load(open(os.path.join(ep.altdir(slug), "base_full.json")))
                m, T = ep.seg_map(slug)
                if ep.face4k:     # face4k-build: one branch per (segment, camera), per-camera drift sync, VFR iPhone -> every frame mapped
                    if "4_sync" not in sync_cache:
                        ok4, det = GA.sync_face4k(ep, slug, "full")
                        sh_ = GA.same_heads(ep, slug)      # the panel layer replays the very same head chains
                        sync_cache["4_sync"] = (ok4 and sh_, {"panel_heads_identical_to_full": sh_, "branches": det})
                    r["4_sync"] = sync_cache["4_sync"]
                elif "seek" not in rec:   # remote2 (per-piece "seeks"): sync is baked per camera via av_offset; this single-seek check doesn't apply
                    r["4_sync"] = (True, {"skipped": "remote2 adapter records per-piece seeks; sync_mapping needs one global seek", "seeks": rec.get("seeks")})
                else:
                    r["4_sync"] = GA.sync_mapping(ep.p(ep.host_cam["path"]), os.path.join(ep.altdir(slug), "filter_base_full.txt"), rec["seek"], m, ep.av, [5.0, 15.0, 25.0])
                r["5_edges"] = GA.edges(path, topf); r["7_size_MB"] = round(os.path.getsize(path) / 1e6, 1)
                if name == "engagement" and ep.face4k:
                    r["6_caption_band"] = GA.anim_band(os.path.join(ep.altdir(slug), "top_anim.mp4"), pcs)
                    r["7a_caption_rows_fixed"] = CAP.rows_fixed(open(os.path.join(ep.altdir(slug), "caps_alt.ass")).read())
                out[name] = {"PASS": all(v[0] for k, v in r.items() if isinstance(v, tuple)) and r["7_size_MB"] < 180, **{k: v for k, v in r.items()}}
            print(json.dumps({slug: out}, indent=1, default=str))
            json.dump({slug: out}, open(os.path.join(ep.edir(slug), "verify.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
