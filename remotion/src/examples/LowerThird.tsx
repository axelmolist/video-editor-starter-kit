import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {SPRING, BRAND, FONT, useBrandFonts} from '../kit';

// Name + role lower third on a TRANSPARENT background, for compositing over footage.
// Render with an alpha codec, e.g. --codec prores --prores-profile 4444 --pixel-format yuva444p10le.
export const LowerThird: React.FC<{name: string; role: string}> = ({name, role}) => {
  useBrandFonts();
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const inS = spring({frame: frame - 4, fps, config: SPRING.enter});
  const outS = spring({frame: frame - (durationInFrames - 14), fps, config: SPRING.soft});
  const v = inS - outS;
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: 120,
          bottom: 140,
          padding: '22px 34px',
          borderLeft: `8px solid ${BRAND.accent}`,
          background: BRAND.background,
          opacity: v,
          transform: `translateX(${interpolate(v, [0, 1], [-30, 0])}px)`,
        }}
      >
        <div style={{fontFamily: FONT.display, fontWeight: 700, fontSize: 56, color: BRAND.text}}>{name}</div>
        <div style={{fontFamily: FONT.body, fontWeight: 600, fontSize: 32, color: BRAND.muted, marginTop: 6}}>{role}</div>
      </div>
    </AbsoluteFill>
  );
};
