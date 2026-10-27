"""Podcast episode - find the best thumbnail frames (frontal face, eyes open, smile).

Samples a frame every N seconds from a close-up, scores each with OpenCV Haar
cascades (frontal face + 2 eyes detected = open + facing camera; smile = bonus),
and prints the top timestamps. Use the best one as --guest-t for make_cutouts.py.

Run with the thumb venv (has opencv-python-headless):
  <thumbnail venv>/bin/python pick_frames.py --video <close-up.mov> [--every 5]
"""
from __future__ import annotations
import argparse, subprocess, tempfile, glob, os
from pathlib import Path
import cv2

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True, type=Path)
ap.add_argument("--every", type=int, default=5, help="sample interval (seconds)")
ap.add_argument("--top", type=int, default=12)
A = ap.parse_args()

fc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
ec = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
sc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")

with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(A.video),
                    "-vf", f"fps=1/{A.every},scale=900:-1", f"{tmp}/f_%04d.png"], check=True)
    rows = []
    for p in sorted(glob.glob(f"{tmp}/f_*.png")):
        t = (int(os.path.basename(p)[2:6]) - 1) * A.every
        img = cv2.imread(p); gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = fc.detectMultiScale(gray, 1.1, 6, minSize=(120, 120))
        if len(faces) == 0:
            continue
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        eyes = ec.detectMultiScale(gray[y:y + int(h * 0.6), x:x + w], 1.1, 6, minSize=(30, 30))
        smile = sc.detectMultiScale(gray[y + int(h * 0.55):y + h, x:x + w], 1.7, 22,
                                    minSize=(int(w * 0.3), int(h * 0.12)))
        center_pen = abs((x + w / 2) - img.shape[1] / 2) / img.shape[1]
        score = (w * h) * (1 if len(eyes) >= 2 else 0.25) * (1.25 if len(smile) else 1.0) * (1 - center_pen)
        rows.append((t, len(eyes), len(smile) > 0, round(score)))
    rows.sort(key=lambda r: -r[3])
    print("t(s)  eyes  smile  score")
    for r in rows[:A.top]:
        print(f"{r[0]:5d}  {r[1]:4d}  {str(r[2]):5}  {r[3]}")
