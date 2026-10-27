import React from 'react';

// One animated beat produced for a video. The animation-generator agent authors these.
export type BeatDef = {
  id: string; // unique render id, e.g. "build-buy-wait--A7"
  component: React.FC;
  width: number; // 1920 for long-form (16:9), 1080 for shorts (9:16)
  height: number; // 1080 for long-form, 1920 for shorts
  durationInFrames: number; // motion length + ~0.5s tail, at 25fps
  fps?: number; // defaults to 25
};
