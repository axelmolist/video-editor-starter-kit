# video/instructions/formats/ - the canonical spec per format

One tool-agnostic spec per format. A human editor or any agent can read one folder and know how to edit that format.
The agent files in `.claude/agents/` are the procedures; these are the rules.

| Format | Spec | Agent |
|---|---|---|
| youtube-long | `youtube-long/longform-youtube-edit-format.md` | `youtube-long-editor` |
| shorts (solo) | `shorts/CLEAN-STYLE.md` (default), `shorts/dynamic-shorts-format.md`, `shorts/OUTPUT-AND-APPROVAL.md` | `shorts-editor` |
| podcast episodes | `podcasts/IN-PERSON-AUDIO.md` | `podcast-editor` |
| podcast shorts | `podcasts/PODCAST-SHORTS-ENGAGEMENT-FORMAT.md` | `podcast-shorts` |
| vlog | `../broll-music-montage-standard.md` + the agent file | `youtube-vlog` |

Everything brand-specific comes from `config/brand.json`. Nothing in these specs names a colour or font directly.
