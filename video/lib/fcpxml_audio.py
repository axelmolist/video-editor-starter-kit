"""Native micro crossfades for raw-media FCPXML asset-clip storylines.

Picture boundaries stay fixed. Audible neighbours get 20 ms of source handles
on both sides of the cut and 40 ms easeInOut fades. Existing J-cuts are retained.
"""
from fractions import Fraction
import xml.etree.ElementTree as ET

def sec(x):return float(Fraction(x.rstrip('s'))) if x else 0.
def rat(x):return f'{round(x*48000)}/48000s'
def audible(c):
 v=c.find('adjust-volume')
 return c.tag=='asset-clip' and c.get('srcEnable')!='video' and (v is None or v.get('amount') not in ('-96dB','-infdB')) and c.get('enabled','1')!='0'
def apply_crossfades(spine, assets):
 clips=list(spine)
 for i,c in enumerate(clips):
  if not audible(c):continue
  a=assets[c.get('ref')];base=sec(a.get('start'));end=base+sec(a.get('duration'));s=sec(c.get('start'));d=sec(c.get('duration'))
  lead=max(0,s-sec(c.get('audioStart',c.get('start'))));trail=sec(c.get('audioDuration',c.get('duration')))-d-lead
  if i and audible(clips[i-1]):lead=max(lead,min(.02,s-base))
  if i+1<len(clips) and audible(clips[i+1]):trail=max(trail,min(.02,end-(s+d)))
  c.set('audioStart',rat(s-lead));c.set('audioDuration',rat(d+lead+trail))
  v=c.find('adjust-volume')
  if v is None:v=ET.Element('adjust-volume',amount='0dB');c.insert(0,v)
  p=v.find('param')
  if p is None:p=ET.SubElement(v,'param',name='amount')
  for tag in ('fadeIn','fadeOut'):
   for x in p.findall(tag):p.remove(x)
  p.insert(0,ET.Element('fadeIn',type='easeInOut',duration='1920/48000s'))
  p.insert(1,ET.Element('fadeOut',type='easeInOut',duration='1920/48000s'))
def assert_crossfades(spine):
 clips=list(spine);count=0
 for a,b in zip(clips,clips[1:]):
  if not(audible(a) and audible(b)):continue
  out=sec(a.get('offset'))+sec(a.get('audioStart',a.get('start')))-sec(a.get('start'))+sec(a.get('audioDuration',a.get('duration')))
  inc=sec(b.get('offset'))+sec(b.get('audioStart',b.get('start')))-sec(b.get('start'))
  if out<=inc+1e-5:raise ValueError(f'No audio overlap: {a.get("name")} -> {b.get("name")}')
  for c in (a,b):
   if c.find('adjust-volume/param/fadeIn') is None or c.find('adjust-volume/param/fadeOut') is None:raise ValueError('Missing native fades')
  count+=1
 return count
