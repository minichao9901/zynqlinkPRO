"""Build a portable Windows bridge EXE plus runtime ZIP (no SDK/Node on user's PC).

AI entry: python toolbox.py bridge-build --out dist/zynq-etm-bridge-win64
The package uses the production Web button and never programs either board.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=('PyInstaller','Flask','Werkzeug','waitress','pyelftools','capstone','numpy','pandas','pyusb','libusb-package','hidapi','pyserial','Jinja2','MarkupSafe','itsdangerous','click')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf8').split('\0')
    # Include new Web modules before their first commit, but never user records.
    names+=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','--','web/app','etm-service/web'],cwd=ROOT).decode('utf8').split('\0')
    return sorted(set(n for n in names if n))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'dist/zynq-etm-bridge-win64',help='新输出目录；拒绝覆盖')
    args=parser.parse_args(argv)
    if os.name!='nt' or sys.maxsize<=2**32:raise ValueError('请使用Windows x64 Python构建')
    out=args.out.resolve()
    archive=Path(str(out)+'.zip')
    if out.exists() or archive.exists():raise ValueError('输出已存在，请选择新目录：'+str(out))
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
        # An in-tree CMake build also contains caches, objects and vendor
        # archives. Only these statically linked runtime tools ship to users.
        native=payload/'build-native';native.mkdir()
        for name in ('etm_decode','etm_frontend','etm_storebuild','etm_index','etm_export','etm_framed'):
            shutil.copyfile(ROOT/'etm-service/build-native'/(name+'.exe'),native/(name+'.exe'))
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
        for path in (ROOT/'etm-service/vendor/OpenCSD-1.8.3/LICENSE',ROOT/'etm-service/vendor/OpenCSD-1.8.3/NOTICES.txt',ROOT/'etm-service/native/SQLITE-LICENSE.txt',Path(sys.base_prefix)/'LICENSE.txt'):
            if path.is_file():shutil.copyfile(path,licenses/(path.parent.name+'-'+path.name))
        readme=('Zynq ETM 工作台\n\n完整解压ZIP，双击 zynq-etm-bridge.exe，浏览器自动打开。请保留_internal目录。\n'
            'Web：载入目标ELF与源码 → 连接探针 → 添加并选择函数起点 → 核对HSE/RCC → 联动采集。\n'
            '目标PLL、AHB/APB分频由target固件负责；桥只配置Trace接口，不自动降频、不烧录板卡。\n'
            '保留F103ZE ETMv3及STM32H743 ETMv4识别/路由/解码；H743 Zynq链路待真机验收。\n'
            '数据在本目录data/records，关闭控制台停止服务；用户无需Python、Node或CLI。\n'
            'AI离线检查：zynq-etm-bridge.exe --check --data-dir CHECK_DIR\n')
        (package/'使用说明.txt').write_text(readme,encoding='utf-8-sig')
        # Validate the frozen runtime before publishing an output directory.
        # No Python/Node/SDK executable is discoverable in this child process.
        environment={k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH')}
        environment['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        checked=subprocess.run([str(package/'zynq-etm-bridge.exe'),'--check','--data-dir',str(work/'check-data')],
            env=environment,capture_output=True,text=True,encoding='utf8',timeout=90)
        if checked.returncode:raise ValueError('冻结EXE离线预检失败：'+checked.stdout+checked.stderr)
        (package/'package-check.json').write_text(json.dumps(json.loads(checked.stdout),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        files=[dict(path=p.relative_to(package).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(package.rglob('*')) if p.is_file()]
        manifest=dict(schema=1,platform='windows-x64',sourceRevision=revision,
            sourceDirty=source_dirty,dependencies=dependencies,
            capturePath='Web button -> Zynq LA -> OpenCSD binary -> C++ TraceStore',
            clockPolicy='target-firmware-owned',requiresSystemPython=False,requiresNode=False,files=files)
        (package/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        out.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(package,out)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for path in sorted(out.rglob('*')):
            if path.is_file():target.write(path,'zynq-etm-bridge/'+path.relative_to(out).as_posix())
    print(json.dumps(dict(ok=True,directory=str(out),exe=str(out/'zynq-etm-bridge.exe'),archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
