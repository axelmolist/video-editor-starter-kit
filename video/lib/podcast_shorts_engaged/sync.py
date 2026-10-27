"""Camera sync for in-person multicam episodes (first used on the multicam build).

The mics share one clock ("mic time"); each camera runs on its own clock with a fixed offset and a slow drift, and its
picture leads the sound by lead0 at t0. Per camera in the episode config:
  sync_off   "a/b+c" offset (Fraction arithmetic, multicam-build: the V1 FCP offset), sync_extra (a compound offset, multicam-build hosts +208 s)
  lead0, ppm (drift), and the episode-level sync.t0
cam_time(mic) = mic + off - round(lead(mic) * 48000) / 48000 + extra,  lead(mic) = lead0 + ppm * 1e-6 * (mic - t0)
(a 1:1 port of the multicam-build project/v3/sync_v3.py model, verified on the clap, a plosive lip release and lip-motion correlation).
"""
from fractions import Fraction as F
import re


def _off(expr):
    s = expr.replace(' ', '')
    parts = re.findall(r'[+-]?[^+-]+', s)
    tot = F(0)
    for p in parts:
        sign = -1 if p.startswith('-') else 1
        p = p.lstrip('+-')
        tot += sign * (F(*map(int, p.split('/'))) if '/' in p else F(p))
    return tot


def cam_time(ep, code, mic):
    c = ep.c['cameras'][code]
    t0 = ep.c['sync']['t0']
    lead = c['lead0'] + c['ppm'] * 1e-6 * (float(mic) - t0)
    return float(F(mic) + _off(c['sync_off']) - F(round(lead * 48000), 48000)) + c.get('sync_extra', 0.0)
