import React from 'react';
import {Composition} from 'remotion';
import {FPS} from './brand';
import {TitleCard} from './examples/TitleCard';
import {LowerThird} from './examples/LowerThird';
import {StatCard} from './examples/StatCard';
import {ShortsBeatExample} from './examples/ShortsBeatExample';
import {LogoSting} from './examples/LogoSting';
import {JOBS} from './jobs';
import {DESIGNS} from './designs';

// Long-form graphics are 16:9. Author at 1920x1080, render with --scale 2 for 3840x2160.
const LAND = {width: 1920, height: 1080};
// Shorts graphics are 9:16. Author at 1080x1920, render with --scale 2 for 2160x3840.
const PORT = {width: 1080, height: 1920};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* Reference beats - living examples of the kit (see src/examples/). */}
      <Composition id="TitleCard" component={TitleCard} durationInFrames={75} fps={FPS} {...LAND}
        defaultProps={{eyebrow: 'Part one', title: 'Where it started'}} />
      <Composition id="LowerThird" component={LowerThird} durationInFrames={125} fps={FPS} {...LAND}
        defaultProps={{name: 'Guest Name', role: 'Founder, Example Co'}} />
      <Composition id="StatCard" component={StatCard} durationInFrames={100} fps={FPS} {...LAND}
        defaultProps={{value: 42, suffix: '%', line: 'of something that matters', source: 'Source: name the source'}} />
      <Composition id="ShortsBeatExample" component={ShortsBeatExample} durationInFrames={95} fps={FPS} {...PORT} />
      <Composition id="LogoSting" component={LogoSting} durationInFrames={60} fps={FPS} {...LAND} />

      {/* Per-video beats, registered via src/jobs/index.ts by the animation-generator agent. */}
      {JOBS.map((b) => (
        <Composition key={b.id} id={b.id} component={b.component} durationInFrames={b.durationInFrames}
          fps={b.fps ?? FPS} width={b.width} height={b.height} />
      ))}

      {/* Standalone animated design cards, registered via src/designs/index.ts. */}
      {DESIGNS.map((d) => (
        <Composition key={d.id} id={d.id} component={d.component} durationInFrames={d.durationInFrames}
          fps={d.fps ?? FPS} width={d.width} height={d.height} />
      ))}
    </>
  );
};
