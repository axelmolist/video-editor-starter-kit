import React from 'react';
import {spring, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Frame, Eyebrow, SPRING, BRAND, FONT} from '../kit';

// Section title card for long-form (16:9). Eyebrow fades in, title lifts and settles, then holds.
export const TitleCard: React.FC<{eyebrow: string; title: string}> = ({eyebrow, title}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - 6, fps, config: SPRING.enter});
  const wipe = spring({frame: frame - 16, fps, config: SPRING.wipe});
  return (
    <Frame gap={36}>
      <Eyebrow dot>{eyebrow}</Eyebrow>
      <div
        style={{
          fontFamily: FONT.display,
          fontWeight: 700,
          fontSize: 132,
          lineHeight: 1,
          letterSpacing: '-0.02em',
          color: BRAND.text,
          opacity: s,
          transform: `translateY(${interpolate(s, [0, 1], [40, 0])}px)`,
        }}
      >
        {title}
      </div>
      <div style={{width: 220 * wipe, height: 8, borderRadius: 4, background: BRAND.accent}} />
    </Frame>
  );
};
