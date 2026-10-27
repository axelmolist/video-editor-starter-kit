import {Config} from '@remotion/cli/config';

// Graphics are composited onto filmed footage, so a PNG image format keeps text crisp.
Config.setVideoImageFormat('png');
// Author at 1080p; render at --scale 2 for native 4K (3840x2160 or 2160x3840).
Config.setConcurrency(4);
