import React from 'react';
import {spring, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Frame, Eyebrow, Label, SPRING, BRAND, FONT} from '../kit';

// VERTICAL shorts template (1080x1920). Same kit, portrait proportions - copy this when
// authoring a beat for the shorts pipeline. Big stat + spring pop is the workhorse layout.
export const ShortsBeatExample: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const countS = spring({frame: frame - 8, fps, config: SPRING.count});
  const value = Math.round(interpolate(countS, [0, 1], [0, 90]));
  const pop = spring({frame: frame - 8, fps, config: SPRING.pop});
  const scale = interpolate(pop, [0, 1], [0.72, 1]);

  return (
    <Frame gap={64}>
      <Eyebrow dot>Example beat</Eyebrow>
      <div
        style={{
          fontFamily: FONT.display,
          fontWeight: 700,
          fontSize: 360,
          lineHeight: 0.9,
          color: BRAND.accent,
          letterSpacing: '-0.04em',
          transform: `scale(${scale})`,
          opacity: countS,
        }}
      >
        {value}%
      </div>
      <div
        style={{
          maxWidth: 820,
          textAlign: 'center',
          fontFamily: FONT.display,
          fontWeight: 700,
          fontSize: 84,
          lineHeight: 1.05,
          color: BRAND.text,
          letterSpacing: '-0.02em',
          opacity: spring({frame: frame - 22, fps, config: SPRING.soft}),
        }}
      >
        one idea per beat
      </div>
      <div style={{marginTop: 20}}>
        <Label delay={34}>replace with a real, sourced number</Label>
      </div>
    </Frame>
  );
};
