import {BeatDef} from '../jobs/_types';

// Standalone animated design cards (MP4 output) - as opposed to jobs/, which are beats
// composited onto footage. Same shape, any canvas size. Per card, create
// `designs/<slug>.tsx` exporting a BeatDef[] and add one import + spread line below.

export const DESIGNS: BeatDef[] = [];
