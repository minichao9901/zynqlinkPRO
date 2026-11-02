"""Offline production-source review checks. No USB, JTAG or board access.

The REPRO checks deliberately assert the current defect, not corrected behavior.
Run from any directory with --out pointing at a new working directory.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out', type=Path, required=True)
args = ap.parse_args()
out = args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
results = []

def run(name, command, timeout=90):
    p = subprocess.run([str(x) for x in command], cwd=ROOT, capture_output=True,
                       text=True, errors='replace', timeout=timeout)
    (out / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
    results.append(dict(name=name, code=p.returncode, output=p.stdout.strip()))
    if p.returncode:
        raise RuntimeError(name + ': ' + (p.stdout + p.stderr)[-3000:])
    print(name + ': ' + p.stdout.strip(), flush=True)

# Reuse the nine existing production C harnesses in an isolated output tree.
driver = (ROOT / 'tools/test_probe_host.py').read_text(encoding='utf-8')
driver = driver.replace("out = root/'build/probe_host'", 'out = Path(' + repr(str(out / 'host')) + ')')
isolated = out / 'baseline_driver.py'
driver = driver.replace('root = Path(__file__).resolve().parents[1]', 'root = Path(' + repr(str(ROOT)) + ')')
isolated.write_text(driver, encoding='utf-8')
run('c_baseline', ['python', '-X', 'utf8', isolated])
mock = out / 'host'
mingw = Path(shutil.which('gcc')).parent.parent
libs = list((mingw / 'lib/gcc/x86_64-w64-mingw32').glob('*'))
cc = ['clang', '--target=x86_64-w64-windows-gnu', '-isystem', mingw / 'include',
      '-L' + str(mingw / 'lib'), '-L' + str(libs[-1])]
includes = ['-I' + str(p) for p in (mock, ROOT/'tools/tests', ROOT/'firmware/xusbps_daplink_dma', ROOT/'firmware/xusbps_daplink_dma/DAP/Include')]

def ctest(name, source, first_include=None):
    src = out / (name + '.c')
    src.write_text(source, encoding='utf-8')
    exe = out / (name + '.exe')
    extra = ['-I' + str(first_include)] if first_include else []
    run(name + '_compile', [*cc, '-std=c11', '-O2', *extra, *includes, src, '-o', exe])
    run(name, [exe])

ctest('restore_failure', r'''
#define main original_test_main
#include "PROBE_TEST"
#undef main
int main(void) {
    probe_target_observe(8,dp_select,1);
    uint32_t original_tar=ap_tar, original_select=dp_select;
    assert(probe_target_claim(20000000)==0);
    assert(probe_target_write_word(0x20000800,0x12345678)==0);
    inject_fault=1;
    probe_target_release();
    assert(!probe_target_claimed());
    assert(ap_tar!=original_tar && dp_select!=original_select);
    printf("REPRO release discards ownership after failed restore: TAR=%08x expected=%08x SELECT=%08x expected=%08x\n",
           ap_tar,original_tar,dp_select,original_select);
    return 0;
}
'''.replace('PROBE_TEST', (ROOT/'tools/tests/probe_target_test.c').as_posix()))

# Include dap_main.c unchanged; mock only external DAP execution / platform.
dapmock = out / 'dapmock'
dapmock.mkdir()
(dapmock/'DAP.h').write_text('''#include "probe_host_platform.h"
#include <string.h>
#define DAP_PACKET_COUNT 16U
#define DAP_PACKET_SIZE 4096U
#define DAP_ENABLE_TRACE 0
extern volatile uint8_t DAP_TransferAbort;
uint32_t DAP_ExecuteCommand(const uint8_t *,uint8_t *);
void DAP_Setup(void);
''')
(dapmock/'dap_metrics.h').write_text('''#include "probe_host_platform.h"
enum {MET_EXEC05,MET_EXEC06_READ,MET_EXEC06_WRITE,MET_USB_SUBMIT,MET_USB_IN,MET_QUEUE_WAIT};
static XTime dap_metric_start(void){return 0;}
static void dap_metric_end(unsigned a,XTime b,uint32_t c){(void)a;(void)b;(void)c;}
''')
for h in ('xil_printf.h', 'sleep.h'):
    (dapmock/h).write_text('#include "probe_host_platform.h"\n')
ctest('dap_ingress', r'''
#include "DAP_MAIN"
volatile uint8_t DAP_TransferAbort;
XUsbPs *g_dap_usb_instance;
static unsigned calls;
static uint32_t observed_clock;
void DAP_Setup(void) {}
void probe_before_dap(void) {}
void probe_after_dap(void) {}
void XUsbPs_DapResumeRx(XUsbPs *p) {(void)p;}
int swd_abort_engines(void) {return 0;}
int XUsbPs_EpBufferSend(XUsbPs *p,u8 ep,u8 *data,u32 n) {(void)p;(void)ep;(void)data;(void)n;return 0;}
int XUsbPs_EpBufferSendWithZLT(XUsbPs *p,u8 ep,u8 *data,u32 n) {return XUsbPs_EpBufferSend(p,ep,data,n);}
uint32_t DAP_ExecuteCommand(const uint8_t *p,uint8_t *q) {
    calls++; if(p[0]==0x11)memcpy(&observed_clock,p+1,4);
    q[0]=p[0];q[1]=0;return 2;
}
int main(void) {
    uint8_t full[]={0x11,0x80,0x96,0x98,0}, short_req[]={0x11};
    chry_dap_state_init();
    usbd_dap_bulk_out(0,1,sizeof full,full);chry_dap_handle();
    usbd_dap_bulk_in(0,1,(void *)tx_final_buffer);
    observed_clock=0;
    usbd_dap_bulk_out(0,1,sizeof short_req,short_req);chry_dap_handle();
    assert(calls==2 && observed_clock==10000000);
    printf("REPRO one-byte SWJ_Clock dispatched with stale 4-byte value %u\n",observed_clock);
    chry_dap_state_init();calls=0;
    uint8_t queued[]={0x7e,1,0,0xf0};
    for(unsigned i=0;i<DAP_PACKET_COUNT;i++)usbd_dap_bulk_out(0,1,sizeof queued,queued);
    for(unsigned i=0;i<100;i++)chry_dap_handle();
    assert(calls==0 && request_in-request_out==16 && !chry_dap_rx_ready());
    puts("REPRO 16 queued commands: no execution, no RX capacity for execute terminator");
    return 0;
}
'''.replace('DAP_MAIN', (ROOT/'firmware/xusbps_daplink_dma/dap_main.c').as_posix()), dapmock)

# Reuse the real controller test wiring, substituting only the stimulus.
tb = (ROOT/'fpga/sim/tb_packet_axi.sv').read_text(encoding='utf-8')
tb = tb.replace('reg [31:0] wdata=0;', "reg [3:0] strobes=15; reg [31:0] wdata=0;")
tb = tb.replace('.s_axi_wstrb(4\'hf)', '.s_axi_wstrb(strobes)')
begin = tb.index(' initial begin\n   #1;rst_n=0;')
end = tb.index(' initial begin #1000000', begin)
tb = tb[:begin] + r'''
 initial begin
   #1;rst_n=0;#20;rst_n=1;
   wr(7'h44,32'h1234);rd(7'h44,status);
   if(status!==32'h1234)$fatal(1,"initial write");
   strobes=0;wr(7'h44,32'h5678);rd(7'h44,status);
   if(status!==32'h5678)$fatal(1,"expected zero-strobe defect absent");
   $display("REPRO WSTRB=0 changes PACKET_LEN from 0x1234 to 0x5678");
   $finish;
 end
''' + tb[end:]
sv = out/'zero_strobe.sv'
sv.write_text(tb, encoding='utf-8')
rtl = sorted((ROOT/'fpga/rtl').glob('*.v'))
exe = out/'zero_strobe.vvp'
run('zero_strobe_compile', ['iverilog','-g2012','-s','tb_packet_axi','-o',exe,*rtl,ROOT/'fpga/sim/xpm_memory_tdpram.sv',sv])
run('zero_strobe', ['vvp',exe])

for top in ['tb_packet_contract','tb_packet_axi','tb_probe_stream_dma',
            'tb_probe_sample_pipe','tb_jtag_pipeline','tb_riscv_pipeline',
            'tb_orbtrace_ddr_writer','tb_orbtrace_ddr_controller','tb_orbtrace_ddr_trace']:
    src=ROOT/'fpga/sim'/f'{top}.sv'
    extra=[ROOT/'fpga/sim/xpm_memory_tdpram.sv']
    if 'module IOBUF' not in src.read_text(encoding='utf-8'):
        extra += [ROOT/'fpga/sim/sim_primitives.v']
    extra += [ROOT/'fpga/sim'/f for f in ('probe_ap_model.sv','jtag_dp_model.sv','jtag_dtm_model.sv','riscv_sba_model.sv') if ('module '+Path(f).stem) not in src.read_text(encoding='utf-8')]
    exe=out/f'{top}.vvp'
    run(top+'_compile',['iverilog','-g2012','-s',top,'-o',exe,*rtl,*extra,src])
    run(top,['vvp',exe])

sources = [*rtl, *sorted((ROOT/'firmware/xusbps_daplink_dma').rglob('*.c')),
           *sorted((ROOT/'firmware/xusbps_daplink_dma').rglob('*.h'))]
summary = dict(base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
               results=results, source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
(out/'results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
