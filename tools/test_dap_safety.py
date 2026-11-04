"""Offline regression of the production DAP preflight and checked executor."""
from pathlib import Path
import argparse,subprocess,shutil,os
ROOT=Path(__file__).resolve().parents[1]
def function(text,signature):
    begin=text.rindex(signature);brace=text.index('{',begin);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[begin:end]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    dap=(ROOT/'firmware/xusbps_daplink_dma/DAP/Source/DAP.c').read_text(encoding='utf8')
    executor=function(dap,'uint32_t DAP_HOT_CODE DAP_ExecuteCommand(')
    (a.out/'dap_checked_executor_under_test.h').write_text('#define DAP_HOT_CODE\n#define DAP_ERROR 255\n#define ID_DAP_Invalid 255\n#define ID_DAP_ExecuteCommands 127\n#define ID_DAP_QueueCommands 126\n'+executor,encoding='utf8')
    cc=['gcc']
    if os.name=='nt' and shutil.which('clang'):
        mingw=Path(shutil.which('gcc')).parent.parent;libs=list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
        cc=['clang','--target=x86_64-w64-windows-gnu','-isystem',str(mingw/'include'),'-L'+str(mingw/'lib'),'-L'+str(libs[-1])]
    exe=a.out/'dap_request_test.exe'
    subprocess.run([*cc,'-std=c11','-O2','-Wall','-Wextra','-I'+str(a.out.resolve()),'-I'+str(ROOT/'firmware/xusbps_daplink_dma/DAP/Include'),str(ROOT/'tools/tests/dap_request_test.c'),str(ROOT/'firmware/xusbps_daplink_dma/DAP/Source/dap_request.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe.resolve())],check=True,timeout=15)
    # Real USB queue entry, with only platform/wire execution dependencies
    # mocked. In particular, reset inside preflight simulates the IRQ window.
    for name in ['xusbps','xil_cache','xil_exception','xil_printf','sleep','xtime_l']:
        (a.out/(name+'.h')).write_text('#include "probe_host_platform.h"\n',encoding='utf8')
    (a.out/'xil_mmu.h').write_text('#include "probe_host_platform.h"\n#define NORM_NONCACHE 0\nstatic inline void Xil_SetTlbAttributes(unsigned a,unsigned b){(void)a;(void)b;}\n',encoding='utf8')
    (a.out/'DAP.h').write_text('#include "probe_target_platform.h"\n#include "dap_request.h"\n#include "dap_wait.h"\n#define DAP_PACKET_SIZE 4096\n#define DAP_PACKET_COUNT 16\n#define DAP_ENABLE_TRACE 0\nextern volatile uint8_t DAP_TransferAbort;\nvoid DAP_Setup(void);\n',encoding='utf8')
    (a.out/'dap_metrics.h').write_text('#include "probe_host_platform.h"\nenum{MET_EXEC05,MET_EXEC06_READ,MET_EXEC06_WRITE,MET_QUEUE_WAIT,MET_USB_IN,MET_USB_SUBMIT};\nstatic XTime dap_metric_start(void){return 0;}\nstatic void dap_metric_end(unsigned a,XTime b,unsigned c){(void)a;(void)b;(void)c;}\n',encoding='utf8')
    exe=a.out/'dap_ingress_safety_test.exe'
    subprocess.run([*cc,'-std=c11','-O2','-Wall','-Wextra','-I'+str(a.out.resolve()),'-I'+str(ROOT/'tools/tests'),'-I'+str(ROOT/'firmware/xusbps_daplink_dma/DAP/Include'),str(ROOT/'tools/tests/dap_ingress_safety_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe.resolve())],check=True,timeout=15)
    # Compile the actual shared wait and the actual SWD/SWJ function bodies;
    # mock only MMIO/time/USB epoch. Real target/PS tests use paired ELFs later.
    sw=(ROOT/'firmware/xusbps_daplink_dma/DAP/Source/SW_DP.c').read_text(encoding='utf8')
    (a.out/'dap_scalar_under_test.h').write_text(function(sw,'uint8_t DAP_HOT_CODE SWD_Transfer(')+'\n'+function(sw,'static void SWJ_SequenceChunk ('),encoding='utf8')
    (a.out/'DAP_config.h').write_text('#include "probe_target_platform.h"\n#define SWD_STATUS 0x40010004U\n',encoding='utf8')
    (a.out/'DAP.h').write_text('#include "probe_target_platform.h"\nextern volatile uint8_t DAP_TransferAbort;\n',encoding='utf8')
    (a.out/'xtime_l.h').write_text('#include "probe_host_platform.h"\n',encoding='utf8')
    exe=a.out/'dap_wait_test.exe'
    subprocess.run([*cc,'-std=c11','-O2','-Wall','-Wextra','-I'+str(a.out.resolve()),'-I'+str(ROOT/'tools/tests'),'-I'+str(ROOT/'firmware/xusbps_daplink_dma/DAP/Include'),str(ROOT/'tools/tests/dap_wait_test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe.resolve())],check=True,timeout=15)
if __name__=='__main__':main()
