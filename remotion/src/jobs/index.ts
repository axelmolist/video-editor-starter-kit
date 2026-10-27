import {BeatDef} from './_types';

// Per-video beats. The animation-generator agent, per video, creates `jobs/<slug>.tsx`
// exporting a BeatDef[] and adds one import + spread line below. Root.tsx registers them all.
//
// Example:
//   import {myVideoBeats} from './my-video';
//   export const JOBS: BeatDef[] = [...myVideoBeats];

export const JOBS: BeatDef[] = [];
