"""Build/update one local Windows bridge directory; ZIP is opt-in.

AI entry: python toolbox.py bridge-build
The package uses the production Web button and never programs either board.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=('PyInstaller','Flask','Werkzeug','waitress','pyelftools','capstone','numpy','pandas','pyusb','libusb-package','hidapi','pyserial','Jinja2','MarkupSafe','itsdangerous','click')
NATIVE_IMAGES=('etm_decode','etm_frontend','etm_storebuild','etm_index','etm_export','etm_framed')


def stamp_web_build(folder):
    path = folder / 'app/core/build.js'
    source = path.read_text(encoding='utf8')
    marker = 'export const WEB_BUILT_AT = null;'
    if source.count(marker) != 1:
        raise ValueError('Web build timestamp placeholder is missing or duplicated')
    built_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    path.write_text(source.replace(marker, 'export const WEB_BUILT_AT = ' + json.dumps(built_at) + ';'),
                    encoding='utf8')
    return built_at


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_desktop_launcher(executable):
    """Give delivered runtime images the normal desktop integrity label.

    Build workspaces can inherit Low MIC. Executing a Low-labelled image lowers
    its process and browser children even from a normal desktop user token.
    Copying the candidate into dist inherits destination labels again.
    """
    if os.name != 'nt':
        return
    executable=Path(executable)
    # Only these package-owned images are executable children. Never relabel
    # the checkout, a directory tree, or anything inside the user's data/.
    images=[executable]+[executable.parent/'_internal/backend/build-native'/(name+'.exe')
                         for name in NATIVE_IMAGES]
    for image in images:
        if image != executable and not image.is_file():continue
        result = subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/icacls.exe'),
            str(image), '/setintegritylevel', 'M'], capture_output=True)
        if result.returncode:
            raise ValueError('无法设置交付程序的标准桌面完整性标签：' + str(image) + '：' +
                             result.stderr.decode('utf8', 'replace'))


def tracked():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf8').split('\0')
    # Include new Web modules before their first commit, but never user records.
    names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','--','web/app','etm-service/web'],cwd=ROOT).decode('utf8').split('\0')
    return sorted(set(n for n in names if n))


def publish_in_place(package,out,previous):
    """ACL fallback: journal program bytes, leaving data/ completely untouched.

    A DENY DELETE_CHILD on dist can forbid renaming its bundle directory while
    still allowing normal file updates. Never change that shared ACL.
    """
    def program_files(folder):
        result={}
        for path in folder.rglob('*'):
            name=path.relative_to(folder)
            if name.parts[0].lower()=='data':continue
            if path.is_symlink():raise ValueError('程序目录不能包含符号链接：'+str(path))
            if path.is_file():result[name]=path
        return result
    old=program_files(out);new=program_files(package)
    previous.mkdir()
    # Finish and verify the complete backup before modifying a single old byte.
    for name,path in old.items():
        target=previous/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        if sha(target)!=sha(path):raise ValueError('归档旧程序校验失败：'+str(name))
    def install(files):
        for name,path in files.items():
            target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target)
            if sha(target)!=sha(path):raise ValueError('程序更新校验失败：'+str(name))
    try:
        install(new)
        prepare_desktop_launcher(out/'zynq-etm-bridge.exe')
        for name in old.keys()-new.keys():(out/name).unlink()
    except BaseException:
        install({name:previous/name for name in old})
        for name in new.keys()-old.keys():
            if (out/name).is_file():(out/name).unlink()
        raise


def publish(package,out,workspace=ROOT):
    """Replace a known local bundle reversibly, preserving its external data."""
    workspace=workspace.resolve();package=package.resolve();out=out.resolve()
    if not out.is_relative_to(workspace) or out in (workspace,workspace/'dist'):
        raise ValueError('输出须为工作区内独立程序目录')
    if out.exists() and (not (out/'package-manifest.json').is_file() or not (out/'zynq-etm-bridge.exe').is_file()):
        raise ValueError('已有目录不是可识别的桥包，拒绝替换：'+str(out))
    if (package/'data').exists():raise ValueError('构建候选不能包含用户数据')
    if (out/'data').exists() and not (out/'data').resolve().is_relative_to(out):
        raise ValueError('数据目录链接到程序目录以外，请先单独保留该数据')
    archive=workspace/'build/bridge-archive'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    archive.mkdir(parents=True,exist_ok=False)
    previous=archive/'previous';old_zip=Path(str(out)+'.zip');saved_zip=archive/'previous.zip'
    def move(source,destination):
        # Validate both absolute targets immediately before every directory move.
        source=source.resolve();destination=destination.resolve()
        if not source.is_relative_to(workspace) or not destination.is_relative_to(workspace):
            raise ValueError('更新移动超出工作区')
        source.rename(destination)
    had_old=out.exists();data_moved=False;zip_moved=False
    if had_old:
        try:move(out,previous)
        except PermissionError:
            # Only this initial rename gets a fallback. Later failures use the
            # ordinary rollback path and are never misclassified as ACL issues.
            if old_zip.exists():
                shutil.copyfile(old_zip,saved_zip)
                if sha(old_zip)!=sha(saved_zip):raise ValueError('旧ZIP归档校验失败')
                old_zip.unlink();zip_moved=True
            try:publish_in_place(package,out,previous)
            except BaseException:
                if zip_moved:shutil.copyfile(saved_zip,old_zip)
                raise
            return dict(previousDirectory=str(previous),dataPreserved=(out/'data').exists(),
                        archiveDirectory=str(archive),publicationMode='verified-file-update')
    try:
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(package,out)
        prepare_desktop_launcher(out/'zynq-etm-bridge.exe')
        if (previous/'data').exists():
            move(previous/'data',out/'data');data_moved=True
        if old_zip.exists():move(old_zip,saved_zip);zip_moved=True
    except BaseException:
        if data_moved:move(out/'data',previous/'data')
        if zip_moved:move(saved_zip,old_zip)
        if out.exists():move(out,archive/'failed-candidate')
        if had_old:move(previous,out)
        raise
    return dict(previousDirectory=str(previous) if had_old else None,
        dataPreserved=data_moved,archiveDirectory=str(archive))


def archive_application(out,archive):
    manifest=json.loads((out/'package-manifest.json').read_text(encoding='utf8'))
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for name in [f['path'] for f in manifest['files']]+['package-manifest.json']:
            path=(out/name).resolve()
            if not path.is_relative_to(out.resolve()) or Path(name).parts[0].lower()=='data':
                raise ValueError('分发包路径不能包含用户数据或超出程序目录')
            target.write(path,'zynq-etm-bridge/'+name)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'dist/zynq-etm-bridge',help='固定本机程序目录；更新时保留data并归档旧程序')
    parser.add_argument('--zip',action='store_true',help='额外生成分发ZIP；本机默认不生成')
    args=parser.parse_args(argv)
    if os.name!='nt' or sys.maxsize<=2**32:raise ValueError('请使用Windows x64 Python构建')
    from tools.verify_dependencies import verify
    source_inputs=verify(ROOT,check_tracked=True)
    if not source_inputs['ok']:
        raise ValueError('构建依赖未完整纳入Git或身份不符：'+'；'.join(source_inputs['failures']))
    shared=subprocess.run([sys.executable,str(ROOT/'tools/sync_etm_shared.py'),'--check'],capture_output=True,text=True)
    if shared.returncode:raise ValueError('ETM共享驱动不是当前主驱动，请先运行web.shared-sync --write：'+shared.stdout+shared.stderr)
    out=args.out.resolve()
    archive=Path(str(out)+'.zip')
    source_dirty=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--','.',
        ':(exclude)build/**',':(exclude)dist/**',':(exclude)releases/**'],cwd=ROOT))
    dependencies={name:importlib.metadata.version(name) for name in DEPENDENCIES}
    from PyInstaller.utils.hooks import collect_submodules
    workbase=ROOT/'build/bridge-package'
    workbase.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='package-',dir=workbase) as temp:
        work=Path(temp);payload=work/'backend';payload.mkdir()
        shutil.copyfile(ROOT/'etm-service/server.py',payload/'server.py')
        modules=[]
        for path in sorted((ROOT/'etm-service/tools').glob('*.py')):
            if path.stem.startswith(('test_','bench_','verify_','generate_')):continue
            destination=payload/'tools'/path.name;destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(path,destination);modules.append(path.stem)
        toolbox=work/'toolbox'
        for name in tracked():
            if name=='web/index.html' or name=='web/package.json' or name.startswith('web/app/'):
                destination=toolbox/Path(name).relative_to('web')
            elif name.startswith('etm-service/web/'):
                destination=payload/Path(name).relative_to('etm-service')
            else:continue
            destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,destination)
        web_built_at = stamp_web_build(toolbox)
        # An in-tree CMake build also contains caches, objects and vendor
        # archives. Only these statically linked runtime tools ship to users.
        native=payload/'build-native';native.mkdir()
        for name in NATIVE_IMAGES:
            shutil.copyfile(ROOT/'etm-service/build-native'/(name+'.exe'),native/(name+'.exe'))
        shutil.copyfile(ROOT/'etm-service/build-native/libdwarf.dll',native/'libdwarf.dll')
        helpers=work/'hosttools';helpers.mkdir()
        shutil.copyfile(ROOT/'tools/dap_pipeline_bench.py',helpers/'dap_pipeline_bench.py')
        golden=work/'prebuilt/golden';golden.mkdir(parents=True)
        shutil.copyfile(ROOT/'prebuilt/golden/f103ze-cdc48.elf',golden/'f103ze-cdc48.elf')
        command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','zynq-etm-bridge',
            '--distpath',str(work/'dist'),'--workpath',str(work/'freeze'),'--specpath',str(work),
            '--add-data',str(payload)+';backend','--add-data',str(toolbox)+';toolbox',
            '--add-data',str(ROOT/'web/tools/dev/serve-etm.py')+';.',
            '--add-data',str(helpers)+';hosttools',
            '--add-data',str(work/'prebuilt')+';prebuilt',
            '--paths',str(ROOT/'etm-service'),'--paths',str(ROOT/'etm-service/tools'),'--paths',str(ROOT/'tools'),
            '--collect-all','capstone','--collect-all','libusb_package',
            '--hidden-import','hid','--hidden-import','serial.tools.list_ports_windows',
            '--hidden-import','usb.backend.libusb1','--hidden-import','waitress',
            '--hidden-import','werkzeug.middleware.dispatcher','--hidden-import','html.parser',
            '--hidden-import','server','--hidden-import','dap_pipeline_bench']
        for name in modules:command+=['--hidden-import',name]
        for package in ('numpy','pandas'):
            for name in collect_submodules(package,filter=lambda n:'tests' not in n.split('.')):
                command+=['--hidden-import',name]
        for name in ('tkinter','matplotlib','scipy','IPython','pytest','PyQt6','PIL','lxml','cryptography'):
            command+=['--exclude-module',name]
        command.append(str(ROOT/'tools/zynq_bridge.py'))
        subprocess.run(command,cwd=ROOT,check=True)
        package=work/'dist/zynq-etm-bridge'
        prepare_desktop_launcher(package/'zynq-etm-bridge.exe')
        examples=package/'examples';examples.mkdir()
        shutil.copyfile(ROOT/'tools/tests/fixtures/h743-etmv4/h743.etmrecord',examples/'h743-superlink-reference.etmrecord')
        shutil.copyfile(ROOT/'tools/tests/fixtures/h743-etmv4/manifest.json',examples/'h743-reference-provenance.json')
        licenses=package/'licenses';licenses.mkdir()
        for name in DEPENDENCIES:
            distribution=importlib.metadata.distribution(name)
            for member in distribution.files or []:
                if any(key in member.name.lower() for key in ('license','copying','notice','copyright')):
                    source=Path(distribution.locate_file(member))
                    if source.is_file():
                        destination=licenses/name/member.name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        for path in (ROOT/'etm-service/vendor/OpenCSD-1.8.3/LICENSE',ROOT/'etm-service/vendor/OpenCSD-1.8.3/NOTICES.txt',ROOT/'etm-service/vendor/nlohmann-json-3.11.3/LICENSE.MIT',ROOT/'etm-service/native/SQLITE-LICENSE.txt',Path(sys.base_prefix)/'LICENSE.txt'):
            if path.is_file():shutil.copyfile(path,licenses/(path.parent.name+'-'+path.name))
        for component,files in [('capstone-5.0.7',('LICENSE.TXT','LICENSE_LLVM.TXT','ZYNQLINK-PROVENANCE.json')),
                                ('libdwarf-2.3.3',('COPYING','src/lib/libdwarf/LGPL.txt','src/lib/libdwarf/LIBDWARFCOPYRIGHT','ZYNQLINK-PROVENANCE.json'))]:
            for name in files:
                source=ROOT/'etm-service/vendor'/component/name
                if source.is_file():
                    destination=licenses/component/Path(name).name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        (licenses/'libdwarf-2.3.3/REBUILD.txt').write_text(
            'Unmodified libdwarf 2.3.3 is distributed as a replaceable native DLL.\n'
            'Matching source: etm-service/vendor/libdwarf-2.3.3 in this project, with upstream URL and archive SHA in ZYNQLINK-PROVENANCE.json.\n'
            'Rebuild: cmake -S etm-service -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release; cmake --build build/native --target dwarf-shared.\n'
            'Replace _internal/backend/build-native/libdwarf.dll with your ABI-compatible build. No application relinking or signature is required.\n',encoding='utf8')
        readme=('Zynq ETM 工作台\n\n双击 zynq-etm-bridge.exe，浏览器自动打开。请保留整个程序目录（包括_internal）。\n'
            'ETM模式默认使用10 MHz SWD做目标配置；CPU/TRACECLK仍由目标固件决定。\n'
            'Web：载入目标ELF与源码 → 连接探针 → 添加并选择函数起点 → 核对HSE/RCC → 联动采集。\n'
            '目标PLL、AHB/APB分频由target固件负责；桥只配置Trace接口，不自动降频、不烧录板卡。\n'
            '保留F103ZE ETMv3及STM32H743 ETMv4；H743 CPU60/TRACECLK20连续CLI采集已验收，Web完整起点流程另验。\n'
            '火焰图：导出双标签HTML，默认Timeline，另有周期权重；左键框选放大、Shift拖动平移。\n'
            'AI离线导出：zynq-etm-bridge.exe --trace-cli export --record RECORD --format flame-html --out flame.html\n'
            '数据在本目录data/records，关闭控制台停止服务；用户无需Python、Node或CLI。\n'
            '可执行手册使用仓库和系统 Python。桥包位于仓库 dist 目录时自动找到仓库，独立解压时用 --workspace 指定。\n'
            'AI离线检查：zynq-etm-bridge.exe --check --data-dir CHECK_DIR\n')
        (package/'使用说明.txt').write_text(readme,encoding='utf-8-sig')
        # Validate the frozen runtime before publishing an output directory.
        # No Python/Node/SDK executable is discoverable in this child process.
        environment={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')}
        environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        checked=subprocess.run([str(package/'zynq-etm-bridge.exe'),'--check','--data-dir',str(work/'check-data')],
            env=environment,capture_output=True,text=True,encoding='utf8',timeout=90)
        if checked.returncode:raise ValueError('冻结EXE离线预检失败：'+checked.stdout+checked.stderr)
        if json.loads(checked.stdout).get('processIntegrityRid', 0) < 8192:
            raise ValueError('冻结启动器仍处于低完整性；候选未发布')
        (package/'package-check.json').write_text(json.dumps(json.loads(checked.stdout),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        wasm=package/'_internal/toolbox/app/core/openocd-runtime/openocd-core.wasm'
        if wasm.read_bytes()[:8]!=b'\0asm\x01\0\0\0':
            raise ValueError('候选包缺少有效的 OpenOCD Wasm')
        files=[dict(path=p.relative_to(package).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(package.rglob('*')) if p.is_file()]
        manifest=dict(schema=1,platform='windows-x64',sourceRevision=revision,webBuiltAt=web_built_at,
            desktopLauncherIntegrity='medium',nativeHelperIntegrity='medium',
            debugBackend=dict(name='OpenOCD Wasm',sha256=sha(wasm),etmControl='mem-ap0',
                scopePolling='target-memory',globalReset='cmsis-dap-swj-pins'),
            etmControlClockDefaultHz=10000000,
            flameHtml=dict(interactive=True,selfContained=True,modes=['timeline','aggregate'],tabs=['timeline','cycles'],defaultTab='timeline',dragSelectZoom=True),offlineTraceCli=True,
            sourceDirty=source_dirty,dependencies=dependencies,
            capturePath='Web button -> Zynq LA -> OpenCSD binary -> C++ TraceStore',
            clockPolicy='target-firmware-owned',requiresSystemPython=False,requiresNode=False,files=files)
        (package/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        # Full offline acceptance of this exact frozen candidate before replacing
        # the local program. Both native protocols, exports and reuse are checked.
        verify=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/verify_bridge_package.py'),
            '--package',str(package),'--out',str(work/'verified'),'--port','0'],capture_output=True,text=True,encoding='utf8',errors='replace')
        verification_output=(verify.stdout or '')+(verify.stderr or '')
        (workbase/'latest-verification-output.txt').write_text(verification_output,encoding='utf8')
        if verify.returncode:raise ValueError('候选EXE离线验收失败，原程序未替换：'+verification_output)
        shutil.copyfile(work/'verified/result.json',workbase/'latest-verification.json')
        publication=publish(package,out)
    result=dict(ok=True,directory=str(out),exe=str(out/'zynq-etm-bridge.exe'),archive=None,**publication)
    if args.zip:
        # Distribute only application files; never include data/records or tokens.
        archive_application(out,archive)
        result.update(archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive))
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
