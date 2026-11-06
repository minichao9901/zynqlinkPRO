"""Stage the public website; publish its GitHub Pages and verified Windows ZIP.

stage is offline. publish pushes only the staged static site to gh-pages.
Authentication comes from Git's credential helper in memory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'minichao9901/zynqlinkPRO'
SITE = 'https://minichao9901.github.io/zynqlinkPRO/'
ASSET = 'zynq-etm-bridge-win64.zip'


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def stage(out):
    out = out.resolve()
    if not out.is_relative_to(ROOT/'build'):
        raise ValueError('Stage directory must be inside build/')
    if out.exists():
        raise ValueError('Use a new stage directory: '+str(out))
    out.mkdir(parents=True)
    # Only tracked frontend assets. No records, binaries, runtime, backend or tokens.
    names = git('ls-files', '--', 'web/index.html', 'web/app').splitlines()
    if not names or 'web/app/download.css' not in names:
        raise ValueError('Commit/add the website inputs before staging')
    for name in names:
        source = ROOT/name
        dest = out/source.relative_to(ROOT/'web')
        if source.is_symlink():
            raise ValueError('Refuse symlink in public website: '+name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    (out/'.nojekyll').write_text('', encoding='utf8')
    # Preserve the bytes bound by site-manifest across Windows Git autocrlf.
    (out/'.gitattributes').write_text('* -text\n',encoding='ascii',newline='\n')
    (out/'README.md').write_text(
        '# ZynqDAP 官方工作台与下载\n\n'
        f'[在线工作台]({SITE}) · [工程下载]({SITE}#download) · '
        f'[Windows 完整包](https://github.com/{REPO}/releases/latest/download/{ASSET})\n\n'
        '使用桌面版 Chrome / Edge。ETM 采集与解码请下载完整包，解压后运行 '
        '`zynq-etm-bridge.exe`；无需 Python / Node。保留 `_internal` 目录。\n\n'
        'gh-pages 分支发布静态前端；正式安装包位于 Releases，不含用户记录或运行令牌。'
        '安装包的来源提交、依赖许可证与逐文件 SHA-256 见包内 manifest / licenses。\n', encoding='utf8')
    manifest = {'sourceRevision':git('rev-parse','HEAD'),
                'files':{p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'site-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    return manifest


class GitHub:
    def __init__(self):
        process = subprocess.run(['git','credential','fill'],cwd=ROOT,
            input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,check=True)
        credentials = dict(line.split('=',1) for line in process.stdout.splitlines() if '=' in line)
        self.headers = {'Authorization':'Bearer '+credentials['password'],
                        'Accept':'application/vnd.github+json','User-Agent':'zynqlinkPRO-release'}

    def request(self,path,method='GET',body=None,content_type='application/json'):
        url = path if path.startswith('https://uploads.github.com/') else 'https://api.github.com'+path
        data = body if isinstance(body,bytes) else json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url,data=data,method=method,
            headers={**self.headers,'Content-Type':content_type})
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = response.read()
            return json.loads(payload) if payload else None

    def upload(self,url,path):
        # Windows' urllib/proxy path can terminate a large TLS write with EOF.
        # Stream through system curl; keep Authorization only on stdin, never
        # in command-line arguments, logs or a temporary credential file.
        config='\n'.join('header = '+json.dumps(k+': '+v) for k,v in self.headers.items())+'\n'
        process=subprocess.run(['curl.exe','--http1.1','--limit-rate','1M','--silent','--show-error','--fail-with-body',
            '--config','-','--request','POST','--header','Content-Type: application/octet-stream',
            '--data-binary','@'+str(path),'--url',url],input=config,
            capture_output=True,text=True,encoding='utf8',timeout=240)
        if process.returncode:
            raise ValueError('Release upload failed: '+process.stderr+' '+process.stdout[:500])
        asset=json.loads(process.stdout)
        if asset['size']!=path.stat().st_size:raise ValueError('Remote upload size differs')
        if asset.get('digest') and asset['digest']!='sha256:'+sha(path):
            raise ValueError('Remote upload SHA differs')
        return asset


def publish(out, package, tag):
    # Refuse unverified/dirty or private-data-containing distribution packages.
    import zipfile
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('zynq-etm-bridge/package-manifest.json'))
        if manifest.get('sourceDirty'):
            raise ValueError('Release requires a clean-source EXE build')
        if any('data' in Path(n).parts or '..' in Path(n).parts for n in names):
            raise ValueError('Release ZIP contains private data or unsafe paths')
        expected = {'zynq-etm-bridge/'+f['path']:f for f in manifest['files']}
        if set(names) != set(expected)|{'zynq-etm-bridge/package-manifest.json'}:
            raise ValueError('ZIP inventory differs from the verified package')
        for name, entry in expected.items():
            data = archive.read(name)
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('ZIP SHA mismatch: '+name)
    site = json.loads((out/'site-manifest.json').read_text(encoding='utf8'))
    for name, expected in site['files'].items():
        if sha(out/name)!=expected:raise ValueError('Staged site changed: '+name)
    api = GitHub()
    repo = api.request('/repos/'+REPO)
    if repo.get('private') or repo.get('full_name')!=REPO:
        raise ValueError('Wrong public distribution repository')
    if not (out/'.git').exists():
        git('init','-b','gh-pages',cwd=out)
        git('remote','add','origin','https://github.com/'+REPO+'.git',cwd=out)
        remote=git('ls-remote','--heads','origin','gh-pages',cwd=out)
        if remote:
            git('fetch','origin','gh-pages',cwd=out)
            git('update-ref','refs/heads/gh-pages',git('rev-parse','FETCH_HEAD',cwd=out),cwd=out)
            git('read-tree','HEAD',cwd=out)
        git('add','--all',cwd=out)
        git('commit','-m','Publish ZynqDAP workbench '+tag,cwd=out)
    git('push','-u','origin','gh-pages',cwd=out)
    try:
        api.request('/repos/'+REPO+'/pages')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        api.request('/repos/'+REPO+'/pages','POST',{'source':{'branch':'gh-pages','path':'/'}})
    # A draft prevents partially uploaded assets from becoming the latest release.
    try:
        release = api.request('/repos/'+REPO+'/releases/tags/'+tag)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        # GET-by-tag can return 404 for an unpublished draft with no Git tag.
        # Reuse that draft after network failures instead of duplicating it.
        release=next((r for r in api.request('/repos/'+REPO+'/releases')
                      if r['tag_name']==tag and r['draft']),None)
        if release is None:release = api.request('/repos/'+REPO+'/releases','POST',{
            'tag_name':tag,'name':'Zynq ETM 工作台 '+tag,'draft':True,
            'body':f'Windows x64 完整便携包，解压后双击 zynq-etm-bridge.exe。保留 _internal；更新前退出旧程序并保留 data。\n\n'
                   f'工程下载：{SITE}#download\n\nSHA-256 ({ASSET}): `{sha(package)}`\n\n'
                   f'EXE 来源提交：`{manifest["sourceRevision"]}`。'
                   '本包不含用户记录或令牌。WebUSB 网页提示由浏览器控制。'})
    if not release['draft']:raise ValueError('Refuse to replace a published release')
    checksums = out.parent/(tag+'-SHA256SUMS.txt')
    checksums.write_text(sha(package)+'  '+ASSET+'\n',encoding='ascii')
    existing={asset['name']:asset for asset in release['assets']}
    for path,name in [(package,ASSET),(checksums,'SHA256SUMS.txt')]:
        if name in existing:
            api.request('/repos/'+REPO+'/releases/assets/'+str(existing[name]['id']),'DELETE')
        api.upload(release['upload_url'].split('{')[0]+'?name='+name,path)
    release=api.request('/repos/'+REPO+'/releases/'+str(release['id']),'PATCH',{'draft':False,'make_latest':'true'})
    return {'site':SITE,'release':release['html_url'],'sha256':sha(package),'siteCommit':git('rev-parse','HEAD',cwd=out)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['stage','publish'])
    parser.add_argument('--out',type=Path,default=ROOT/'build/github-pages-release')
    parser.add_argument('--package',type=Path,default=ROOT/'dist/zynq-etm-bridge.zip')
    parser.add_argument('--tag',default='v1.3.0')
    args=parser.parse_args()
    result=stage(args.out) if args.action=='stage' else publish(args.out.resolve(),args.package.resolve(),args.tag)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
