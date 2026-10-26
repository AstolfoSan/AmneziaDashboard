"""Normalize reviewed screenshot captures without cropping, resizing or metadata."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
NAMES=[kind+'-'+lang for kind in ('dashboard','devices','expiry','join','setup-direct','setup-cascade') for lang in ('ru','en')]


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
    output=ROOT/'docs/images';output.mkdir(parents=True,exist_ok=True);hashes={}
    for name in NAMES:
        source=args.source/(name+('.jpg' if name.startswith('setup-') else '.png'))
        with Image.open(source) as captured:
            # New RGB image carries no EXIF, comments, text chunks or source paths.
            clean=Image.new('RGB',captured.size);clean.paste(captured.convert('RGB'))
            target=output/(name+'.png');clean.save(target,format='PNG',optimize=True)
        hashes[target.relative_to(ROOT).as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    print(json.dumps(hashes,indent=2))
