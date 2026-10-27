#!/usr/bin/env python3
"""Face track for the engagement shorts (MediaPipe FaceLandmarker, IMAGE mode, 5 fps).

Needs mediapipe (pip install mediapipe) and the face landmarker model
(https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task).

For every camera with kind "tracked" in the episode config, samples every short's segments +-1 s at the camera's
picture time (mic time + av_offset) and writes the camera's `face_track` file:
    {slug: [[mic_t, mouth_y, mouth_x, box_top, box_h], ...]} in SOURCE pixels.
box_top = landmark 10 (top of the forehead), box_h = chin (152) - landmark 10, mouth = mean of the inner lips (13, 14),
mouth_x = face centre (mean of landmarks 234 and 454: stable when the head turns).

usage: track_faces.py <episode.json> --model face_landmarker.task [slug ...]
"""
import argparse, json, os, subprocess, sys
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from podcast_shorts_engaged.config import Episode  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("episode"); ap.add_argument("--model", required=True); ap.add_argument("slugs", nargs="*")
a = ap.parse_args()
ep = Episode(a.episode)
DW, DH = 1920, 1080
det = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
    base_options=mpt.BaseOptions(model_asset_path=a.model), running_mode=vision.RunningMode.IMAGE, num_faces=1))
slugs = a.slugs or ep.slugs()
for code, cam in ep.c["cameras"].items():
    if cam.get("kind") != "tracked" or not cam.get("face_track"):
        continue
    out_p = ep.p(cam["face_track"])
    out = json.load(open(out_p)) if os.path.exists(out_p) else {}
    k = cam["src_w"] / DW
    for slug in slugs:
        rows = []
        for a0, a1 in ep.short(slug)["segs"]:
            t0 = a0 - 1.0; dur = a1 - a0 + 2.0
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0 + cam.get('av_offset', 0.0):.3f}", "-i", ep.p(cam["path"]),
                                  "-t", f"{dur:.3f}", "-vf", f"fps=5,scale={DW}:{DH},format=rgb24", "-f", "rawvideo", "-"],
                                 capture_output=True).stdout
            for i, f in enumerate(np.frombuffer(raw, np.uint8).reshape(-1, DH, DW, 3)):
                r = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(f)))
                if not r.face_landmarks:
                    continue
                L = r.face_landmarks[0]
                y = lambda j: L[j].y * DH * k; x = lambda j: L[j].x * DW * k  # noqa: E731
                rows.append([round(t0 + i / 5, 2), round((y(13) + y(14)) / 2, 1), round((x(234) + x(454)) / 2, 1),
                             round(y(10), 1), round(y(152) - y(10), 1)])
        out[slug] = sorted(rows); print(code, slug, len(rows))
    os.makedirs(os.path.dirname(out_p), exist_ok=True)
    json.dump(out, open(out_p, "w"))
