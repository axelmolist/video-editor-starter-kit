import React from 'react';
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {Frame, SPRING, BRAND, FONT, BRAND_NAME} from '../kit';
import generated from '../brand.generated.json';

// Short logo sting for intros/outros. Uses the light logo copied to public/brand/ by
// scripts/apply_brand.py; falls back to the brand name in the title font if there is none.
export const LogoSting: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - 4, fps, config: SPRING.pop});
  const wipe = spring({frame: frame - 14, fps, config: SPRING.wipe});
  const style = {transform: `scale(${interpolate(s, [0, 1], [0.85, 1])})`, opacity: s};
  return (
    <Frame gap={40}>
      {generated.logo ? (
        <Img src={staticFile(generated.logo)} style={{...style, height: 220}} />
      ) : (
        <div style={{...style, fontFamily: FONT.display, fontWeight: 700, fontSize: 150, color: BRAND.text}}>{BRAND_NAME}</div>
      )}
      <div style={{width: 360 * wipe, height: 6, borderRadius: 3, background: BRAND.accent}} />
    </Frame>
  );
};
