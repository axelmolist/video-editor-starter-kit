"""
Example HTML/CSS scene generator (HyperFrames) - CONSTANT-MOTION version.

Motion rule: a graphic is ALWAYS moving while on screen. One continuous
burst per beat (no start-stop-start, no static holds). Bars move together or
immediately after each other. The motion's climax lands the section's key point.
As soon as motion ends, the scene is gone within ~0.5s (composite alpha fade).
Scenes are short (~2-4s) and placed to climax on the key word; face fills the rest.

Brand: palette roles and fonts come from config/brand.json (via kitconfig.py): titles in the
title font and accent colour, labels in the body font's real weights, text colour = works /
accent = fails, fonts via local(), no lines through text.

usage: python build-scenes.example.py <edit_dir> <hyperframes_scaffold_dir>
"""
import os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import kitconfig  # noqa: E402

EDIT, SCAFFOLD = sys.argv[1], sys.argv[2]
_P = kitconfig.palette(); _F = kitconfig.brand()["fonts"]

HEAD = """<!doctype html><html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face{font-family:"AN";src:local("BODY_FONT");font-weight:400}
@font-face{font-family:"AN";src:local("BODY_FONT_BOLD");font-weight:700}
@font-face{font-family:"ANC";src:local("TITLE_FONT")}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;
 background:BG_HEX;
 font-family:"AN","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased;color:TEXT_HEX}
#root{position:relative;width:1080px;height:1920px}
.kick{position:absolute;width:100%;text-align:center;font-weight:700;letter-spacing:9px;color:MUTED_HEX;font-size:40px}
.title{position:absolute;width:100%;text-align:center;font-family:"ANC";color:ACCENT_HEX;font-size:120px;line-height:1.0}
.big{position:absolute;width:100%;text-align:center;font-family:"ANC";font-size:300px;line-height:1;color:ACCENT_HEX}
.sub{position:absolute;width:100%;text-align:center;font-weight:700;font-size:52px;letter-spacing:2px;color:TEXT_HEX}
.muted{position:absolute;width:100%;text-align:center;font-weight:600;font-size:36px;letter-spacing:5px;color:MUTED_HEX}
.node{position:absolute;width:150px;text-align:center}
.dot{width:34px;height:34px;border-radius:50%;border:5px solid TEXT_HEX;margin:0 auto}
.dot.accent{border-color:ACCENT_HEX;background:ACCENT_HEX}
.nl{font-weight:700;font-size:34px;margin-top:18px}
.nl.accent{color:ACCENT_HEX}
.line{position:absolute;height:4px;background:MUTED_HEX;transform-origin:left center}
.bar{position:absolute;bottom:0;border-radius:14px 14px 4px 4px;transform-origin:bottom center;
 background:linear-gradient(180deg,#fff 0%,#dfe6f0 100%);box-shadow:0 18px 50px rgba(0,0,0,.45)}
.glyph{position:absolute;border:6px solid MUTED_HEX;border-radius:24px}
</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-duration="DUR" data-width="1080" data-height="1920">
BODY
</div>
<script>
window.__timelines=window.__timelines||{};
const tl=gsap.timeline({paused:true});
SCRIPT
window.__timelines["main"]=tl;
</script></body></html>"""
for _k, _v in {"BODY_FONT_BOLD": _F["body"].get("bold_name", _F["body"]["name"]), "BODY_FONT": _F["body"]["name"],
               "TITLE_FONT": _F["title"]["name"], "BG_HEX": _P["background"], "TEXT_HEX": _P["text"],
               "MUTED_HEX": _P["muted"], "ACCENT_HEX": _P["accent"]}.items():
    HEAD = HEAD.replace(_k, _v)


# --- SCENE: hook ---
hook = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:520px">FOR</div>
<div class="big clip" data-start="0" data-duration="D" data-track-index="2" id="ten" style="top:610px">10</div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="3" style="top:1000px;color:MUTED_HEX;font-family:'ANC';font-size:96px">YEARS</div>
<div class="glyph clip" data-start="0" data-duration="D" data-track-index="4" id="phone" style="left:486px;top:1200px;width:108px;height:188px"></div>
<div class="muted clip" data-start="0" data-duration="D" data-track-index="5" style="top:1450px">COLD CALLING</div>
""", """
tl.from(".kick",{opacity:0,y:-18,duration:.35},0);
tl.from("#ten",{opacity:0,scale:.6,duration:.45,ease:"back.out(2)"},.12);
tl.from(".sub",{opacity:0,y:18,duration:.35},.45);
tl.from("#phone",{opacity:0,y:22,duration:.4,ease:"power3.out"},.7);
tl.from(".muted",{opacity:0,duration:.35},.95);
""", 1.9)

# --- SCENE: 25 on the phones (counter, continuous count = motion) ---
count25 = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:640px">EVERY SINGLE DAY</div>
<div class="big clip" data-start="0" data-duration="D" data-track-index="2" id="cnt" style="top:740px">25</div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="3" style="top:1120px">ON THE PHONES</div>
""", """
tl.from(".kick",{opacity:0,y:-16,duration:.3},0);
const o={v:0};tl.to(o,{v:25,duration:1.4,ease:"power1.out",onUpdate:()=>document.getElementById('cnt').textContent=Math.round(o.v)},.15);
tl.from("#cnt",{opacity:0,scale:.7,duration:.4,ease:"back.out(2)"},.15);
tl.from(".sub",{opacity:0,y:16,duration:.4},.6);
""", 2.1)

# --- SCENE: telecoms engine flow -> it works (continuous) ---
tele = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:560px">THE TELECOMS ENGINE</div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="2" id="n1" style="left:150px;top:760px"><div class="dot"></div><div class="nl">DIAL</div></div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="3" id="n2" style="left:465px;top:760px"><div class="dot"></div><div class="nl">FIELD</div></div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="4" id="n3" style="left:780px;top:760px"><div class="dot accent"></div><div class="nl accent">CLOSE</div></div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="5" id="l1" style="left:300px;top:777px;width:180px"></div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="6" id="l2" style="left:615px;top:777px;width:180px"></div>
<div class="muted clip" data-start="0" data-duration="D" data-track-index="7" style="top:960px">HIGH TOUCH . LONG CONTRACTS</div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="8" id="works" style="top:1140px;font-size:72px">IT WORKS</div>
""", """
tl.from(".kick",{opacity:0,y:-16,duration:.3},0);
tl.from("#n1",{opacity:0,scale:.4,duration:.3,ease:"back.out(2)"},.2);
tl.from("#l1",{scaleX:0,duration:.3},.42);
tl.from("#n2",{opacity:0,scale:.4,duration:.3,ease:"back.out(2)"},.6);
tl.from("#l2",{scaleX:0,duration:.3},.82);
tl.from("#n3",{opacity:0,scale:.4,duration:.35,ease:"back.out(2)"},1.0);
tl.from(".muted",{opacity:0,y:10,duration:.4},1.45);
tl.from("#works",{opacity:0,scale:1.2,duration:.5,ease:"back.out(2)"},1.95);
""", 3.0)

# --- SCENE: contrast (bars move back-to-back, verdict immediately, continuous) ---
con = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:240px">WHY THE MODEL BREAKS</div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="2" id="cost" style="left:150px;top:560px;width:780px;border-top:3px dashed MUTED_HEX;background:none;height:0"></div>
<div class="muted clip" data-start="0" data-duration="D" data-track-index="3" style="top:495px;text-align:right;width:920px;font-size:30px;letter-spacing:4px">HIGH-TOUCH COST</div>
<div class="bar clip" data-start="0" data-duration="D" data-track-index="4" id="bh" style="left:230px;top:560px;width:200px;height:660px"></div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="5" style="top:1255px;left:180px;width:300px;font-size:40px">HIGH PRICE</div>
<div class="bar clip" data-start="0" data-duration="D" data-track-index="7" id="bl" style="left:650px;top:920px;width:200px;height:300px"></div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="8" style="top:1250px;left:600px;width:300px;font-size:40px">LOW PRICE</div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="9" id="gap" style="left:748px;top:560px;width:0;height:360px;border-left:4px dashed ACCENT_HEX;background:none;transform-origin:top center"></div>
<div class="muted clip" data-start="0" data-duration="D" data-track-index="10" id="sf" style="top:700px;left:800px;width:240px;text-align:left;color:ACCENT_HEX;font-size:30px">SHORTFALL</div>
<div class="title clip" data-start="0" data-duration="D" data-track-index="11" id="verdict" style="top:1430px;font-size:104px">THE NUMBERS<br/>DON'T ADD UP</div>
""", """
tl.from(".kick",{opacity:0,y:-16,duration:.3},0);
tl.from("#cost",{scaleX:0,transformOrigin:"left",duration:.5,ease:"power3.out"},.25);
tl.from("#bh",{scaleY:0,duration:.7,ease:"power3.out"},.65);
tl.from("#bl",{scaleY:0,duration:.7,ease:"power3.out"},1.0);
tl.from("#gap",{scaleY:0,opacity:0,duration:.4},1.85);
tl.from("#sf",{opacity:0,x:-8,duration:.3},2.15);
tl.from("#verdict",{opacity:0,scale:1.2,duration:.55,ease:"back.out(2)"},2.55);
""", 3.7)

# --- SCENE: new engine -> people to attention (continuous) ---
new = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:300px">A DIFFERENT ENGINE</div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="2" id="m1" style="left:120px;top:560px"><div class="dot"></div><div class="nl">CONTENT</div></div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="3" id="m2" style="left:465px;top:560px"><div class="dot"></div><div class="nl">AUDIENCE</div></div>
<div class="node clip" data-start="0" data-duration="D" data-track-index="4" id="m3" style="left:810px;top:560px"><div class="dot"></div><div class="nl">ORGANIC</div></div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="5" id="ml1" style="left:270px;top:577px;width:210px"></div>
<div class="line clip" data-start="0" data-duration="D" data-track-index="6" id="ml2" style="left:615px;top:577px;width:210px"></div>
<div class="sub clip" data-start="0" data-duration="D" data-track-index="7" id="ppl" style="top:1000px;color:MUTED_HEX;font-size:60px">PEOPLE</div>
<div class="big clip" data-start="0" data-duration="D" data-track-index="8" id="ar" style="top:1080px;font-size:84px;color:MUTED_HEX">&#8595;</div>
<div class="title clip" data-start="0" data-duration="D" data-track-index="9" id="att" style="top:1320px;font-size:128px">ATTENTION</div>
""", """
tl.from(".kick",{opacity:0,y:-16,duration:.3},0);
tl.from("#m1",{opacity:0,scale:.4,duration:.3,ease:"back.out(2)"},.2);
tl.from("#ml1",{scaleX:0,duration:.28},.42);
tl.from("#m2",{opacity:0,scale:.4,duration:.3,ease:"back.out(2)"},.6);
tl.from("#ml2",{scaleX:0,duration:.28},.82);
tl.from("#m3",{opacity:0,scale:.4,duration:.3,ease:"back.out(2)"},1.0);
tl.from("#ppl",{opacity:0,y:14,duration:.35},1.5);
tl.from("#ar",{opacity:0,y:-16,duration:.35},1.85);
tl.from("#att",{opacity:0,scale:1.2,duration:.55,ease:"back.out(2)"},2.2);
""", 3.3)

# --- SCENE: cta (continuous in + slow drift = still moving) ---
cta = ("""
<div class="kick clip" data-start="0" data-duration="D" data-track-index="1" style="top:760px">FOLLOW</div>
<div class="title clip" data-start="0" data-duration="D" data-track-index="2" id="ctaT" style="top:840px;font-size:150px">THE<br/>TRANSITION</div>
""", """
tl.from(".kick",{opacity:0,y:-16,duration:.35},0);
tl.from("#ctaT",{opacity:0,scale:1.2,duration:.5,ease:"back.out(2)"},.25);
tl.to("#ctaT",{scale:1.04,duration:1.4,ease:"sine.inOut"},.9);
""", 2.3)

SCENES = {"hook": hook, "count25": count25, "telecoms": tele, "contrast": con, "newengine": new, "cta": cta}

for name, (body, script, dur) in SCENES.items():
    d = os.path.join(EDIT, "scenes", name); os.makedirs(d, exist_ok=True)
    for f in ("hyperframes.json", "meta.json", "package.json"):
        src = os.path.join(SCAFFOLD, f)
        if os.path.exists(src): shutil.copy(src, d)
    html = HEAD.replace("DUR", str(dur)).replace("BODY", body.replace('data-duration="D"', f'data-duration="{dur}"')).replace("SCRIPT", script)
    open(os.path.join(d, "index.html"), "w").write(html)
    print(f"{name}: dur {dur}s")
print("done")
