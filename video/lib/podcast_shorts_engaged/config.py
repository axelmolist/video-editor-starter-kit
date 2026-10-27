"""Episode config for the podcast-shorts ENGAGEMENT format.

One JSON file per episode (see episodes/example.json). All times in a short's
plan are HOST-AUDIO time (the per-mic transcripts' clock; in person = the shared mic clock) unless a key says "out"
(output seconds on the short's own timeline). Paths in the JSON are relative to `episode_dir`, which is relative to
the repo root.

Optional keys (all backward compatible; reference-build uses none of them):
  shorts_dir_files   a directory (relative to the episode JSON's own folder) of <slug>.json files, each one short's
                     block, merged into c["shorts"] (file wins over an inline block of the same slug). Lets parallel
                     agents each own one short file instead of clobbering a shared JSON.
  camera_mode        "in_person_multicam" -> multicam.py plan_layer / plan_audio (multicam-build: 3 people, shared/own 1080p cams, sync.py offset model)
  adapter            "face4k" -> face4k.py (face4k-build: own 4K cams incl. a VFR iPhone, linear drift sync, chin-led framing)
  grid_camera        the camera whose frame grid every segment is snapped to (default host_camera)
  cameras.<k>.sync   {"slope", "intercept"}: a per-camera LINEAR drift model, cam_time = t + slope*t + intercept.
                     When present the camera's A/V offset is evaluated per short (at its first segment) instead of the
                     constant av_offset; layer branches evaluate it per segment.
  shorts.<slug>.owner  "host" (default) or "guest": whose short it is. A guest-owned short opens the guest mic and
                     shows the guest camera by default; the host becomes the listener (gated mic, reaction cutaways).

Spec: video/instructions/formats/podcasts/PODCAST-SHORTS-ENGAGEMENT-FORMAT.md
"""
import glob, json, os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class Episode:
    def __init__(self, path, shorts_root=None):
        self.path = os.path.abspath(path)
        self.c = json.load(open(self.path))
        d = self.c.get("shorts_dir_files")
        if d:
            self.c.setdefault("shorts", {})
            for f in sorted(glob.glob(os.path.join(os.path.dirname(self.path), d, "*.json"))):
                self.c["shorts"][os.path.splitext(os.path.basename(f))[0]] = json.load(open(f))
        self.ep_dir = os.path.join(REPO, self.c["episode_dir"])
        # shorts_root lets a dry run write into a scratch copy instead of the episode folder
        self.shorts_dir = shorts_root or os.path.join(self.ep_dir, self.c.get("shorts_dir", "shorts"))
        self.fps = self.c["fps"]; self.W = self.c["out_w"]; self.H = self.c["out_h"]
        self.host_cam = self.c["cameras"][self.c.get("host_camera", "A")]

    def p(self, rel):
        """episode-relative path -> absolute"""
        return rel if os.path.isabs(rel) else os.path.join(self.ep_dir, rel)

    def short(self, slug): return self.c["shorts"][slug]
    def slugs(self): return list(self.c["shorts"])
    def edir(self, slug): return os.path.join(self.shorts_dir, slug, "editor-files")
    def altdir(self, slug): return os.path.join(self.edir(slug), "alt")
    def final_dir(self, slug): return os.path.join(self.shorts_dir, slug, "final-footage")

    # the host camera's clock defines the frame grid every segment is snapped to
    @property
    def av(self): return self.host_cam["av_offset"]
    @property
    def v_start(self): return self.host_cam["v_start"]

    # ---- per-camera sync (constant offset, or a linear drift model) ----
    def cam(self, code): return self.c["cameras"][code]

    def cam_time(self, code, t):
        """picture time on camera `code` for audio time t"""
        k = self.cam(code)
        if "sync" in k: return t + k["sync"]["slope"] * t + k["sync"]["intercept"]
        return t + k["av_offset"]

    def grid_cam(self): return self.c.get("grid_camera", self.c.get("host_camera", "A"))

    def av_of(self, slug):
        """A/V offset of the grid camera for this short (constant, or the drift model at the short's first segment;
        drift inside one short is < 5 ms on face4k-build)"""
        if "av" in self.short(slug): return self.short(slug)["av"]     # per-short owner grid (multicam-build multicam, make_config.py)
        g = self.grid_cam(); k = self.cam(g)
        if "sync" not in k: return k["av_offset"]
        t = self.short(slug)["segs"][0][0]
        return self.cam_time(g, t) - t

    def v_start_of(self, slug):
        if "v_start" in self.short(slug): return self.short(slug)["v_start"]
        return self.cam(self.grid_cam()).get("v_start", 0.0)


    def seg_map(self, slug):
        from . import timeline as TL
        if self.c.get("segment_snap") == "audio":
            # face4k-build (face4k): audio-exact segments. The in-edge stays on the measured silence (no frame-grid shift, which
            # would push tight word-gap cuts up to 20 ms into speech); the duration is n whole frames (the authored segs
            # are already frame multiples, out-edge rounded to the quieter side); the picture anchors on the nearest real
            # source frame (<= 20 ms, inside the sync gate). Output timing stays exact: t0 = sum of n / fps.
            m, T = [], 0.0
            for a0, a1 in self.short(slug)["segs"]:
                n = int(round((a1 - a0) * self.fps)); m.append((a0, a0 + n / self.fps, n, T)); T += n / self.fps
            return m, T
        return TL.seg_map(self.short(slug)["segs"], self.fps, self.v_start_of(slug), self.av_of(slug))

    # ---- who owns the short ----
    def owner(self, slug): return self.short(slug).get("owner", "host")

    def owner_cam(self, slug):
        return self.c.get("other_camera", "S") if self.owner(slug) == "guest" else self.c.get("host_camera", "A")

    def listener_cam(self, slug):
        return self.c.get("host_camera", "A") if self.owner(slug) == "guest" else self.c.get("other_camera", "S")

    def mics(self, slug):
        """(owner_wav, owner_transcript, other_wav, other_transcript): the owner's mic is the open one, the other
        person's mic is gated open only in the short's reply windows"""
        a = self.c["audio"]
        h = (self.p(a["host_wav"]), self.p(a["host_transcript"])); o = (self.p(a["other_wav"]), self.p(a["other_transcript"]))
        return (*o, *h) if self.owner(slug) == "guest" else (*h, *o)

    # ---- camera-adapter switches (multicam-build camera_mode / face4k-build adapter) ----
    @property
    def multicam(self): return self.c.get("camera_mode") == "in_person_multicam"
    @property
    def face4k(self): return self.c.get("adapter") == "face4k"
    def cam_kind(self, code): return self.cam(code).get("kind", "tracked")
