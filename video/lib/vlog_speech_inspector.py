"""Self-contained, read-only acoustic speech-entry measurement.

Uses local Silero VAD with a 32ms window plus a 5ms high-pass energy envelope.
It reports evidence, never edits media or certifies phonetic correctness.
"""
import numpy as np
from scipy.signal import butter,sosfilt
import onnxruntime as ort

def make_inspector(model):
 opt=ort.SessionOptions();opt.intra_op_num_threads=1;opt.inter_op_num_threads=1
 sess=ort.InferenceSession(str(model),sess_options=opt,providers=['CPUExecutionProvider'])
 def inspect_head(samples,start,end,words):
  sr=16000;left=max(0,start-.5);right=min(len(samples)/sr,end,start+2.)
  seg=np.asarray(samples[int(left*sr):int(right*sr)],dtype=np.float32)
  state=np.zeros((2,1,128),np.float32);ctx=np.zeros((1,64),np.float32);probs=[]
  for i in range(0,len(seg),512):
   ch=np.pad(seg[i:i+512],(0,max(0,512-len(seg[i:i+512]))))[None,:];p,state=sess.run(None,{'input':np.concatenate([ctx,ch],axis=1),'state':state,'sr':np.array(sr,np.int64)});ctx=ch[:,-64:];probs.append(float(p[0,0]))
  hp=sosfilt(butter(2,130,fs=sr,btype='highpass',output='sos'),seg)
  n=len(hp)//80;env=np.sqrt(np.mean(hp[:n*80].reshape(n,80)**2,axis=1)+1e-14) if n else np.array([])
  db=20*np.log10(env+1e-12);t=left+np.arange(len(db))*.005
  head=(t>=start-.02)&(t<=min(end,start+1.))
  local=db[head];noise=float(np.percentile(db,12)) if len(db) else -100;peak=float(np.percentile(local,95)) if len(local) else -100
  threshold=max(-64,min(peak-24,noise+9))
  near=[w for w in words if w.get('end',0)>start-.02 and w.get('start',0)<min(end,start+1.8)]
  first=near[0] if near else None
  vadstart=next((left+i*.032 for i,p in enumerate(probs) if p>.25 and left+(i+1)*.032>start),None)
  # Preserve consonants preceding voiced syllables; do not mistake ASR timestamp
  # or detector latency for permission to discard them.
  candidates=np.where(head&(db>=threshold))[0]
  onset=None
  for k in candidates:
   if np.count_nonzero(db[k:k+4]>=threshold)>=2:
    tt=float(t[k]);support=vadstart is not None and tt>=vadstart-.20
    lexical=first is not None and first['start']-.10<=tt<=first['end']+.04
    if support or lexical:onset=max(start,tt);break
  return dict(onset=onset,first_word=first,energy_threshold_db=round(threshold,2),noise_db=round(noise,2),peak_db=round(peak,2),vad_onset=vadstart,max_vad_probability=max(probs,default=0),method='Silero VAD plus 5ms high-pass energy with lexical protection')
 return inspect_head
