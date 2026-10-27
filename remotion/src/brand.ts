import type React from 'react';
// Generated from config/brand.json by scripts/apply_brand.py (npm run brand). Never edit the
// generated file by hand and never hard-code a colour or font name in a composition: change
// config/brand.json and rerun `npm run brand`.
import generated from './brand.generated.json';

export const BRAND = {
  background: generated.palette.background,
  primary: generated.palette.primary,
  accent: generated.palette.accent,
  text: generated.palette.text,
  muted: generated.palette.muted,
  // subtle raised-card fill and hairlines, derived so they work on any dark or light background
  card: 'rgba(255,255,255,0.04)',
  cardBorder: 'rgba(255,255,255,0.06)',
  hairline: 'rgba(255,255,255,0.10)',
} as const;

export const FONT = {
  display: generated.fonts.title,
  body: generated.fonts.body,
  captions: generated.fonts.captions,
  mono: 'ui-monospace, SFMono-Regular, Menlo, monospace',
} as const;

export const BRAND_NAME: string = generated.brand_name;
export const FPS: number = generated.fps;

// Full-frame backdrop: a soft radial lift of the background colour. Use as a full-frame layer.
export const bgStyle: React.CSSProperties = {
  position: 'absolute',
  inset: 0,
  background: `radial-gradient(120% 100% at 50% 0%, ${BRAND.primary} 0%, ${BRAND.background} 65%)`,
};
