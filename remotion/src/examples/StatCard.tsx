import React from 'react';
import {spring, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Frame, Label, SPRING, BRAND, FONT} from '../kit';

// Long-form stat card (16:9): a number counts up, its line lands, then it holds still.
export const StatCard: React.FC<{value: number; suffix: string; line: string; source: string}> = ({
  value,
  suffix,
  line,
  source,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const c = spring({frame: frame - 6, fps, config: SPRING.count});
  const n = Math.round(interpolate(c, [0, 1], [0, value]));
  return (
    <Frame gap={28}>
      <div style={{fontFamily: FONT.display, fontWeight: 700, fontSize: 300, lineHeight: 0.9, color: BRAND.accent}}>
        {n}
        {suffix}
      </div>
      <div
        style={{
          fontFamily: FONT.body,
          fontWeight: 700,
          fontSize: 64,
          color: BRAND.text,
          opacity: spring({frame: frame - 20, fps, config: SPRING.soft}),
        }}
      >
        {line}
      </div>
      <Label delay={30}>{source}</Label>
    </Frame>
  );
};
