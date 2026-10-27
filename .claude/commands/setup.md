---
description: Run (or rerun) onboarding - brand, palette, fonts, logos, captions, keys, engines - then the doctor check
---

Run the onboarding described in `AGENTS.md` under "First run: onboarding comes before anything else".

- If `config/brand.json` already exists, this is a rerun: show the current values in a short table and ask which
  sections to change. Keep everything else as it is.
- Ask a few questions at a time. Write answers as you go. Secrets go only in `.env`.
- Finish with `python3 scripts/apply_brand.py`, `scripts/doctor.sh` and the brand proof still.
- Write `config/.setup-complete` (today's date) only when the doctor reports no FAIL.

$ARGUMENTS
