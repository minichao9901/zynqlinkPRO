"""Offline verification of curated ETM records; USB access is explicitly blocked."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]

def validate(records):
    sys.path.insert(0,str(ROOT/'etm-service'));sys.path.insert(0,str(ROOT/'tools'))
    def forbidden(*args,**kwargs):raise RuntimeError('Hardware access forbidden in offline record verification')
    with patch('usb.core.find',side_effect=forbidden):
        spec=importlib.util.spec_from_file_location('retained_record_server',ROOT/'etm-service/server.py')
        server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
        server.RECORDS=records;server.Vis=forbidden;client=server.app.test_client();rows=[]
        for endpoint in ['/api/profiles','/api/default-elf']:
            response=client.get(endpoint);assert response.status_code==200,(endpoint,response.get_json());response.close()
        for folder in sorted(records.iterdir()):
            if not folder.is_dir() or not (folder/'session.json').exists():continue
            sid=folder.name;checks=[]
            for endpoint in [f'/api/records/{sid}',f'/api/record-elf/{sid}',f'/api/browse/{sid}/overview',f'/api/browse/{sid}/page?view=events&offset=913&limit=20',f'/api/browse/{sid}/window?fromSeq=913&toSeq=977&bins=20',f'/api/browse/{sid}/issues?limit=10']:
                response=client.get(endpoint);assert response.status_code==200,(endpoint,response.get_json());checks.append(endpoint);response.close()
            sources=server.result(sid)['sources'];key=next(k for k,v in sources.items() if v)
            response=client.get(f'/api/browse/{sid}/source?file='+quote(key,safe=''));assert response.status_code==200 and response.get_json()['text'];response.close()
            for mode in ['timeline','aggregate']:
                response=client.get(f'/api/download/{sid}/flame-svg?mode={mode}&weight=records&fromSeq=913&toSeq=977')
                assert response.status_code==200 and b'<svg' in response.data;response.close()
            response=client.get(f'/api/download/{sid}/raw');assert response.status_code==200
            expected=json.loads((folder/'session.json').read_text())['etmSha256'];assert hashlib.sha256(response.data).hexdigest()==expected;response.close()
            rows.append(dict(id=sid,passed=True,rawSHA256=expected,nativeIntermediateRetained=(folder/'native.bin').exists(),checks=checks))
        return dict(hardwareAccess=False,records=rows)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,default=ROOT/'etm-service/records')
    parser.add_argument('--out',type=Path)
    args=parser.parse_args();value=validate(args.records.resolve());text=json.dumps(value,indent=2)+'\n'
    if args.out:args.out.write_text(text,encoding='utf8')
    else:print(text,end='')

if __name__=='__main__':main()
