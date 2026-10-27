// Brand spring presets - use these instead of ad-hoc configs so every beat shares the
// same motion feel. Pass into remotion's spring({frame, fps, config: SPRING.enter}).
export const SPRING = {
  // primary element entrance (opacity + lift): soft, premium settle
  enter: {damping: 16, mass: 0.9, stiffness: 120},
  // number / accent pop with a touch of overshoot
  pop: {damping: 10, mass: 0.7, stiffness: 130},
  // underline / bar wipe
  wipe: {damping: 18, stiffness: 90},
  // labels, eyebrows, subs - clean fade-in, no overshoot
  soft: {damping: 20, stiffness: 90},
  // grid dots / small repeated elements
  dot: {damping: 14, mass: 0.6, stiffness: 150},
  // slow count-up so a number eases into its target
  count: {damping: 18, mass: 1.1, stiffness: 70},
} as const;
