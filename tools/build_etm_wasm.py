"""Build the project's browser OpenCSD decoder with an activated Emscripten SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emsdk',type=Path,default=Path(os.environ.get('EMSDK',ROOT/'build/emsdk')))
    parser.add_argument('--jobs',type=int,default=4)
    args=parser.parse_args()
    sdk=args.emsdk.resolve();emcmake=sdk/'upstream/emscripten/emcmake.py'
    if not emcmake.is_file():parser.error('Activate Emscripten 4.0.10, then pass --emsdk <directory>')
    env=os.environ.copy();env['EM_CONFIG']=str(sdk/'.emscripten')
    out=ROOT/'build/etm_wasm'
    subprocess.run([sys.executable,str(emcmake),'cmake','-S',str(ROOT/'web/etm-native'),'-B',str(out),'-G','Ninja','-DCMAKE_BUILD_TYPE=Release'],env=env,check=True)
    subprocess.run(['cmake','--build',str(out),'--target','zynqdap_etm','--parallel',str(args.jobs)],env=env,check=True)
    target=ROOT/'web/app/etm'
    for name in ('opencsd.mjs','opencsd.wasm'):shutil.copy2(out/name,target/name)
    version=subprocess.check_output([sys.executable,str(sdk/'upstream/emscripten/emcc.py'),'--version'],env=env,text=True).splitlines()[0]
    source_files=[*(ROOT/'web/etm-native').rglob('*'),*(ROOT/'third_party/OpenCSD-1.8.3').rglob('*')]
    source_hash=hashlib.sha256()
    for file in sorted(f for f in source_files if f.is_file()):
        source_hash.update(file.relative_to(ROOT).as_posix().encode());source_hash.update(file.read_bytes())
    manifest={'compiler':version,'opencsd':'1.8.3','source_sha256':source_hash.hexdigest(),
              'artifacts':{name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in ('opencsd.mjs','opencsd.wasm')},
              'options':['Release','-O3','-fexceptions','MODULARIZE','EXPORT_ES6','ALLOW_MEMORY_GROWTH','MEMFS','FS','callMain']}
    (target/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(target/'opencsd.wasm')
if __name__=='__main__':main()
