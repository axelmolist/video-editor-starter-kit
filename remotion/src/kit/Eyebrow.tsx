import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {BRAND, FONT} from '../brand';
import {SPRING} from './springs';

/** Mono, letter-spaced, uppercase eyebrow/kicker with an optional accent dot. */
export const Eyebrow: React.FC<{
  children: React.ReactNode;
  delay?: number;
  size?: number;
  dot?: boolean;
}> = ({children, delay = 0, size = 34, dot = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, config: SPRING.soft});
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: size * 0.5,
        fontFamily: FONT.mono,
        fontWeight: 500,
        fontSize: size,
        letterSpacing: '0.42em',
        textTransform: 'uppercase',
        color: BRAND.muted,
        opacity: s,
      }}
    >
      {dot ? (
        <span
          style={{width: size * 0.42, height: size * 0.42, borderRadius: '50%', background: BRAND.accent}}
        />
      ) : null}
      {children}
    </div>
  );
};

/** Small mono caption label (e.g. under a diagram). */
export const Label: React.FC<{children: React.ReactNode; delay?: number; size?: number}> = ({
  children,
  delay = 0,
  size = 26,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: frame - delay, fps, config: SPRING.soft});
  return (
    <div
      style={{
        fontFamily: FONT.mono,
        fontWeight: 500,
        fontSize: size,
        letterSpacing: '0.24em',
        textTransform: 'uppercase',
        color: BRAND.muted,
        opacity: s,
        textAlign: 'center',
      }}
    >
      {children}
    </div>
  );
};
