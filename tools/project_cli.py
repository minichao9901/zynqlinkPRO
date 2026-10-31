"""Discover and run versioned project entrypoints without a browser.

list/describe and run --dry-run only inspect source and construct a plan.
run preserves the underlying tool's stdout/stderr and exit code. Tool arguments
must follow --; no shell command strings are accepted.
"""
import argparse
import ast
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ROOTS=('tools/','fpga/','firmware/target/','firmware/boot/','etm-service/','web/tools/','web/bridge/')
EXCLUDED={'vendor','sdk','reference','records','build-native','node_modules','tests','selftest','as_run_helpers'}
EXTENSIONS={'.py','.tcl','.ps1','.mjs'}
ALIASES={
 'fpga.build':'fpga/build_dma.tcl','fpga.incremental':'fpga/build_incremental.tcl',
 'fpga.verify':'fpga/verify_routed.tcl','fpga.7010':'fpga/implement_7010.tcl',
 'fpga.repair-io':'fpga/repair_probe_io.tcl','sim.cm3':'tools/run_cm3_sim.py','sim.matrix':'tools/run_cm3_matrix.py',
 'firmware.build':'tools/build_xusbps_daplink.py','firmware.ocm':'tools/report_ocm_elf.py',
 'boot.build':'tools/build_probe_boot.py','boot.package':'tools/package_probe_boot.py',
 'probe.load':'tools/download_dap_fpga.tcl','probe.flash':'tools/probe_flash.py','probe.ocm-verify':'tools/verify_probe_ocm_code.py',
 'bench.sram':'tools/benchmark_sram_matrix.py','bench.rtt':'tools/benchmark_rtt_forward.py',
 'bench.hss':'tools/benchmark_hss_matrix.py','bench.sota':'tools/run_sota_regression.py',
 'probe.regression':'tools/run_probe_regression.py','etm.cli':'etm-service/trace.py',
 'etm.sweep':'tools/f103_trace_sweep.py','etm.samples':'tools/trace_signal_analysis.py',
 'etm.bench':'tools/bench_etm_native_offline.py','etm.web-bench':'tools/bench_etm_native_browser.py',
 'etm.fixture':'tools/prepare_etm_offline_fixture.py','etm.equivalence':'tools/verify_etm_native_equivalence.py',
 'etm.records-check':'tools/verify_retained_records.py',
 'target.fixtures':'tools/build_f103_fixtures.py','target.cdc-build':'firmware/target/stm32f103_cdc_trace/build.ps1',
 'target.cdc-tests':'firmware/target/stm32f103_cdc_trace/tests/run_tests.ps1',
 'target.scope-build':'firmware/target/stm32f103_scope/build.ps1','target.hpm-build':'firmware/target/hpm5301_perf/build.ps1',
 'native.build':'etm-service/build-decoder.ps1',
}
WORKFLOWS={
 'web.check':('Web全部模块语法检查（源码入口无需bundle构建）',[('node',['web/tools/dev/check-syntax.mjs'])]),
 'test.web':('Web主机自测',[('node',['--test','web/tools/selftest/*.test.mjs'])]),
 'test.cli':('统一CLI主机自测',[('python',['-m','unittest','discover','-s','tools/tests','-p','test_toolbox*.py'])]),
}
SUPPORT_TCL={'compact_config.tcl','run_threads.tcl','configure_runs.tcl','configure_ip_cache.tcl','ps7_init.tcl','ps7_config.tcl','probe_rtl.tcl','probe_io_timing.tcl','axi_pipeline.tcl'}


def paths(root=ROOT):
    try:
        output=subprocess.check_output(['git','ls-files','-z'],cwd=root,stderr=subprocess.DEVNULL)
        found=output.decode('utf8').split('\0')
    except (OSError,subprocess.CalledProcessError):
        found=[]
        for prefix in ROOTS:
            base=root/prefix
            if not base.exists():continue
            for folder,dirs,files in os.walk(base):
                dirs[:]=[d for d in dirs if d not in EXCLUDED and not d.startswith(('build','.'))]
                found.extend((Path(folder)/name).relative_to(root).as_posix() for name in files)
    return sorted(set(p for p in found if p))


def main_guard(tree):
    for node in tree.body:
        if isinstance(node,ast.If) and isinstance(node.test,ast.Compare) and any(isinstance(op,ast.Eq) for op in node.test.ops):
            text=ast.unparse(node.test)
            if '__name__' in text and '__main__' in text:return True
    return False


def describe_file(path,root=ROOT):
    source=(root/path).resolve()
    if not source.is_relative_to(root.resolve()) or not source.is_file():raise ValueError('工具文件不在当前项目内：'+path)
    text=source.read_text(encoding='utf-8-sig');suffix=source.suffix.lower()
    flags=[];subcommands=[];summary='';runnable=True
    if suffix=='.py':
        tree=ast.parse(text);runnable=main_guard(tree);summary=(ast.get_docstring(tree) or '').split('\n\n')[0]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                if node.func.attr=='add_argument':flags.extend(a.value for a in node.args if isinstance(a,ast.Constant) and isinstance(a.value,str) and a.value.startswith('-'))
                if node.func.attr=='add_parser':subcommands.extend(a.value for a in node.args[:1] if isinstance(a,ast.Constant) and isinstance(a.value,str))
        runtime='python'
    elif suffix=='.ps1':runtime='powershell'
    elif suffix=='.mjs':runtime='node'
    else:
        runtime='xsct' if re.search(r'\b(connect|targets|mrd|mwr|dow|hsi::)\b',text) else 'vivado'
        runnable=source.name not in SUPPORT_TCL and not source.name.endswith('_bd.tcl') and '/bd/' not in path
    if not summary:
        comments=[line.lstrip('#/ *').strip() for line in text.splitlines()[:15] if line.lstrip().startswith(('#','//'))]
        summary=next((line for line in comments if line and not line.startswith('!')),source.stem)
    legacy=path.startswith('etm-service/tools/h743/') or (suffix=='.mjs' and path.startswith('etm-service/tools/'))
    category=('fpga' if path.startswith('fpga/') else 'target' if path.startswith('firmware/target/') else
              'boot' if 'boot' in source.stem or path.startswith('firmware/boot/') else
              'web-build' if path.startswith('web/') else 'etm' if path.startswith('etm-service/') or any(x in source.stem for x in ['etm','trace','orbtrace']) else
              'build' if source.stem.startswith('build') else 'validation' if source.stem.startswith(('test','run','verify','check','accept')) else
              'benchmark' if any(x in source.stem for x in ['bench','sota']) else 'diagnostic')
    covered_by=('toolbox.py trace decode/query/export' if path.startswith('etm-service/tools/') else 'project run fpga.build / fpga.verify' if path.startswith('fpga/') else None) if not runnable else None
    return {'id':path,'source':path,'runtime':runtime,'category':category,'summary':summary[:800],
            'runnable':runnable,'coveredBy':covered_by,'role':'legacy-entry' if legacy and runnable else 'reference-entry' if path.startswith('etm-service/tools/') and runnable else 'entry' if runnable else 'support-library',
            'sourceOptions':sorted(set(flags)),'sourceSubcommands':sorted(set(subcommands)),
            'environmentKeys':sorted(set(re.findall(r'env\(([A-Za-z_][A-Za-z0-9_]*)\)',text))),
            'requiresBrowser':bool(re.search(r'playwright|puppeteer|connectOverCDP',text)),
            'validation':'not inferred from discoverability','aliases':[k for k,v in ALIASES.items() if v==path]}


@lru_cache(maxsize=4)
def inventory(root=ROOT):
    entries=[]
    candidates=set(paths(root))
    candidates.update(v for v in ALIASES.values() if (root/v).is_file())
    # Include the dispatcher itself when generating the initial catalog before its first commit.
    if (root/'tools/project_cli.py').is_file():candidates.add('tools/project_cli.py')
    for path in sorted(candidates):
        p=Path(path)
        if not path.startswith(ROOTS) or p.suffix.lower() not in EXTENSIONS:continue
        if path not in ALIASES.values() and any(part in EXCLUDED or part.startswith('build') for part in p.parts[:-1]):continue
        try:entries.append(describe_file(path,root))
        except (SyntaxError,UnicodeError):
            entries.append({'id':path,'source':path,'runnable':False,'role':'unparsed-source','category':'needs-review','runtime':None})
    for name,(summary,steps) in WORKFLOWS.items():
        entries.append({'id':name,'source':None,'runnable':True,'role':'workflow','runtime':'workflow','category':'validation' if name.startswith('test.') else 'web-build','summary':summary,'steps':steps,'aliases':[],'requiresBrowser':False,'validation':'not inferred from discoverability'})
    return entries


def executable(runtime):
    if runtime=='python':return sys.executable
    if runtime=='node':return shutil.which('node')
    if runtime=='powershell':return shutil.which('pwsh') or shutil.which('powershell')
    if runtime in ('vivado','xsct'):
        found=shutil.which(runtime)
        if found:return found
        base=Path('E:/Xilinx/Vivado/2018.3/bin/vivado.bat' if runtime=='vivado' else 'E:/Xilinx/SDK/2018.3/bin/xsct.bat')
        return str(base) if base.is_file() else None
    return None


def resolve(name,root=ROOT):
    selected=ALIASES.get(name,name)
    match=next((e for e in inventory(root) if e['id']==selected),None)
    if not match:raise ValueError('未知项目工具：'+name)
    return match


def plan(name,args=(),env=None,root=ROOT):
    entry=resolve(name,root)
    if not entry['runnable']:raise ValueError('这是支持库/上下文脚本，请通过其构建或Trace/Web上层入口调用：'+name)
    env=env or {}
    if not isinstance(env,dict) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',k) or not isinstance(v,str) for k,v in env.items()):raise ValueError('--env-json必须为环境变量名到字符串的字典')
    if any(k.upper() in ('HOME','CODEX_HOME') for k in env):raise ValueError('项目环境参数不能覆盖HOME/CODEX_HOME')
    steps=[]
    if entry['role']=='workflow':
        for runtime,base in entry['steps']:steps.append({'runtime':runtime,'executable':executable(runtime),'arguments':list(base),'cwd':str(root)})
        steps[-1]['arguments']+=list(args)
    else:
        runtime=entry['runtime'];source=str((root/entry['source']).resolve())
        if runtime=='python':arguments=['-X','utf8',source,*args]
        elif runtime=='powershell':arguments=['-NoProfile','-File',source,*args]
        elif runtime=='node':arguments=[source,*args]
        else:arguments=list(args)
        steps.append({'runtime':runtime,'executable':executable(runtime),'arguments':arguments,'cwd':str(root),
                      **({'tclSource':source,'adapter':'source with literal Tcl argv'} if runtime in ('xsct','vivado') else {})})
    return {'id':entry['id'],'requestedName':name,'steps':steps,'environment':env,'effects':'same as the underlying registered tool; no tool runs during planning','output':'underlying stdout/stderr and exit code are preserved','dependencyValidation':'interpreter discovery only; SDK/vendor/hardware requirements remain tool-specific'}


def tcl_wrapper(source,args):
    literal=lambda value:'[encoding convertfrom utf-8 [binary format H* {'+str(value).encode('utf8').hex()+'}]]'
    return 'set argv [list '+ ' '.join(literal(a) for a in args)+']\nset argc [llength $argv]\nset argv0 '+literal(source)+'\nsource '+literal(source)+'\n'


def execute(value):
    environment={**os.environ,**value['environment']}
    for step in value['steps']:
        if not step['executable']:raise ValueError('未找到所需工具链：'+step['runtime'])
        if step.get('tclSource'):
            with tempfile.TemporaryDirectory(prefix='zynq-project-') as folder:
                wrapper=Path(folder)/'launch.tcl';wrapper.write_text(tcl_wrapper(step['tclSource'],step['arguments']),encoding='utf8')
                # User Tcl arguments live inside a hex-encoded script, never in a batch command line.
                if os.name=='nt' and any(re.search(r'[&|<>^%!\r\n]',str(x)) for x in (step['executable'],wrapper)):
                    raise ValueError('SDK批处理启动路径包含命令解释符；请使用普通工具链/TEMP目录')
                args=['-mode','batch','-source',str(wrapper)] if step['runtime']=='vivado' else [str(wrapper)]
                code=subprocess.call([step['executable'],*args],cwd=step['cwd'],env=environment)
        else:code=subprocess.call([step['executable'],*step['arguments']],cwd=step['cwd'],env=environment)
        if code:return code
    return 0


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    split=argv.index('--') if '--' in argv else len(argv);child=argv[split+1:] if split<len(argv) else []
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    listing=sub.add_parser('list');listing.add_argument('--out');listing.add_argument('--all',action='store_true',help='包括支持库/非独立脚本');listing.add_argument('--category')
    info=sub.add_parser('describe');info.add_argument('name');info.add_argument('--out')
    run=sub.add_parser('run');run.add_argument('name');run.add_argument('--dry-run',action='store_true');run.add_argument('--env-json',default='{}');run.add_argument('--out')
    a=p.parse_args(argv[:split])
    try:
        if a.out and Path(a.out).exists():raise ValueError('拒绝覆盖结果文件：'+a.out)
        if a.action=='list':
            entries=inventory();filtered=[e for e in entries if (a.all or e['runnable']) and (not a.category or e['category']==a.category)]
            value={'protocol':'project-cli/1','entries':filtered,'counts':{'indexed':len(entries),'runnable':sum(e['runnable'] for e in entries),'support':sum(not e['runnable'] for e in entries)},'validation':'Entry coverage is not hardware/function acceptance.'}
        elif a.action=='describe':value=resolve(a.name)
        else:
            value=plan(a.name,child,json.loads(a.env_json))
            if not a.dry_run:
                if a.out:raise ValueError('实际执行保留工具原生输出；--out仅用于清单/描述/--dry-run')
                return execute(value)
        output=json.dumps({'ok':True,'value':value},ensure_ascii=False,indent=2)+'\n'
        if a.out:Path(a.out).write_text(output,encoding='utf8')
        else:print(output,end='')
        return 0
    except (OSError,ValueError) as error:
        print(json.dumps({'ok':False,'error':str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
