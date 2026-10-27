import React from 'react';
import {AbsoluteFill} from 'remotion';
import {BRAND, bgStyle} from '../brand';
import {useBrandFonts} from '../fonts';

/**
 * Full-frame brand backdrop for every video beat. Loads brand fonts (delayRender, so no
 * frame is ever captured in a fallback font) and paints the brand background used
 * across the video graphics. Works at any composition size - landscape (1920x1080) for
 * long-form, vertical (1080x1920) for shorts.
 *
 * `center` (default true) vertically+horizontally centres children in a column.
 */
export const Frame: React.FC<{
  children: React.ReactNode;
  center?: boolean;
  gap?: number;
}> = ({children, center = true, gap}) => {
  useBrandFonts();
  return (
    <AbsoluteFill style={{backgroundColor: BRAND.background}}>
      <div style={bgStyle} />
      {center ? (
        <AbsoluteFill
          style={{alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap}}
        >
          {children}
        </AbsoluteFill>
      ) : (
        children
      )}
    </AbsoluteFill>
  );
};
