"""Run SDK 2018.3 native tools with SDK DLLs local to an isolated launcher.

The vendor batch loader can return success after a Windows DLL load failure.
No SDK/system files or global environment variables are changed.
"""
import os
from pathlib import Path
import shutil
import pefile

ROOT=Path(__file__).resolve().parents[1]


def prepare(sdk,tool):
    if tool not in ('hsi','bootgen','rdi_zynq_flash'):raise ValueError('Unsupported SDK tool')
    sdk=Path(sdk).resolve()
    work_root=Path(os.environ.get('ZYNQLINK_WORK_DIR',str(ROOT.parent/'zynqlinkPRO-work')))
    work=(work_root/'runtime'/('sdk-'+tool)).resolve()
    resource_root=sdk
    work.mkdir(parents=True,exist_ok=True)
    search=[sdk/x for x in ('bin/unwrapped/win64.o','lib/win64.o','tps/win64',
                            'tps/win64/jre/bin','tps/win64/jre/bin/server')]
    seen=set()
    def copy(path):
        if path.name.lower() in seen:return
        seen.add(path.name.lower());destination=work/path.name
        if not destination.exists() or destination.stat().st_size!=path.stat().st_size:
            shutil.copyfile(path,destination)
        pe=pefile.PE(str(path),fast_load=True)
        pe.parse_data_directories(directories=[1])
        for item in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            name=item.dll.decode()
            dependency=next((folder/name for folder in search if (folder/name).is_file()),None)
            if dependency:copy(dependency)
        pe.close()
    copy(sdk/'bin/unwrapped/win64.o'/(tool+'.exe'))
    if tool=='hsi':
        for name in ('librdi_commontasks.dll','librdi_hsmtasks.dll',
                     'librdi_boardcommontasks.dll','librdi_boardhsitasks.dll'):
            copy(sdk/'lib/win64.o'/name)
    env=os.environ.copy()
    env.update(RDI_APPROOT=str(resource_root),HDI_APPROOT=str(resource_root),RDI_BINROOT=str(resource_root/'bin'),
        RDI_DATADIR=str(resource_root/'data'),RDI_BINDIR=str(resource_root/'bin/unwrapped/win64.o'),
        RDI_LIBDIR=str(resource_root/'lib/win64.o'),RDI_BASEROOT=str(resource_root.parent),
        XILINX_SDK=str(resource_root),XILINX_PLANAHEAD=str(resource_root),
        RDI_JAVAROOT=str(sdk/'tps/win64/jre'),
        RDI_PLATFORM='win64',RDI_OPT_EXT='.o',TCL_LIBRARY=str(sdk/'tps/tcl/tcl8.5'),
        JAVA_HOME=str(sdk/'tps/win64/jre'))
    env['PATH']=';'.join(map(str,[work,*search]))+';'+env.get('PATH','')
    if tool=='rdi_zynq_flash':
        env['RDI_NO_JRE']='yes'
        env['XIL_CSE_ZYNQ_DISPLAY_UBOOT_MESSAGES']='1'
    return work/(tool+'.exe'),env
