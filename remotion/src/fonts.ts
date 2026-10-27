import {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import generated from './brand.generated.json';

// Brand faces copied into public/fonts by scripts/apply_brand.py from config/brand.json.
// The render is blocked (delayRender) until they load, so no frame is ever captured in a
// fallback font. If a face has no file, it must be installed on the system instead; Chrome
// then resolves it by name.
type Face = {family: string; weight: string; file: string};
const FACES: Face[] = generated.faces;

const loadFace = (f: Face) => {
  const face = new FontFace(f.family, `url(${staticFile('fonts/' + f.file)})`, {weight: f.weight});
  return face.load().then((loaded) => {
    (document.fonts as FontFaceSet).add(loaded);
  });
};

/** Call at the top of any composition. Blocks the first frame until brand fonts load. */
export const useBrandFonts = () => {
  const [handle] = useState(() => delayRender('loading brand fonts'));
  useEffect(() => {
    let cancelled = false;
    Promise.all(FACES.map(loadFace))
      .then(() => !cancelled && continueRender(handle))
      .catch(() => !cancelled && continueRender(handle));
    return () => {
      cancelled = true;
    };
  }, [handle]);
};
