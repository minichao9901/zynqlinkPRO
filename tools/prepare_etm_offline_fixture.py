"""Restore a hash-verified 1s ETM benchmark record from Git-tracked files, with no board access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'docs/validation/native-engine-offline-20261031/fixture/manifest.json'


def prepare(output,fixture=DEFAULT):
    fixture=Path(fixture).resolve();manifest=json.loads(fixture.read_text(encoding='utf8'))
    if manifest.get('schema')!='etm-offline-fixture/1':raise ValueError('unsupported ETM fixture schema')
    inputs=[]
    for name,item in manifest['files'].items():
        if Path(name).name!=name:raise ValueError('fixture output must be a file name')
        source=(ROOT/item['repoPath']).resolve()
        if not source.is_relative_to(ROOT):raise ValueError('fixture source must be in this checkout')
        if source.stat().st_size!=item['bytes'] or hashlib.sha256(source.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('fixture hash/size mismatch: '+item['repoPath'])
        inputs.append((name,source,item['sha256']))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    for name,source,expected in inputs:
        shutil.copyfile(source,output/name)
        assert hashlib.sha256((output/name).read_bytes()).hexdigest()==expected
    report={'hardwareAccess':False,'fixture':str(fixture),'record':str(output),
            'files':{name:sha for name,_,sha in inputs}}
    (output/'fixture-restoration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fixture',type=Path,default=DEFAULT)
    a=p.parse_args();print(json.dumps(prepare(a.out,a.fixture),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
