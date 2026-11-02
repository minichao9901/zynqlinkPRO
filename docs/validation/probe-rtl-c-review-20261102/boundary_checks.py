"""Additional offline checks of unchanged production C function bodies.

External MMIO/DMA are mocked; no hardware access. REPRO means defect observed.
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess

root = Path(__file__).resolve().parents[3]
ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--out', type=Path, required=True)
out = ap.parse_args().out.resolve()
out.mkdir(parents=True, exist_ok=False)
mingw = Path(shutil.which('gcc')).parent.parent
libs = list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
cc = ['clang', '--target=x86_64-w64-windows-gnu', '-isystem', str(mingw/'include'),
      '-L'+str(mingw/'lib'), '-L'+str(libs[-1]), '-O2', '-std=c11']

def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

dap = (root/'firmware/xusbps_daplink_dma/DAP/Source/DAP.c').read_text(encoding='utf-8')
hdr = (root/'firmware/xusbps_daplink_dma/DAP/Include/DAP.h').read_text(encoding='utf-8')
defs = '\n'.join(line for line in hdr.splitlines() if re.match(r'#define (DAP_TRANSFER_|DP_RDBUFF|ID_DAP_TransferBlock)', line))
block = function(dap, 'static uint32_t DAP_SWD_TransferBlock(')
source = r'''
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
typedef uint64_t XTime;
static uint32_t swd_dma_cmd[1024],swd_dma_rsp[1024];
static unsigned DAP_TransferAbort;
static struct {unsigned xfer_block_batch,xfer_block_batch_read_words,xfer_block_batch_write_words;} DAP_SWD_Stats;
static unsigned dbg_pkt_taken,dbg_pkt_fallback,dbg_pkt_status,dbg_pkt_rsp0,dbg_pkt_req,dbg_pkt_count;
enum {SWD_PACKET_STATUS,SWD_PACKET_LEN,SWD_PACKET_CTRL,MET_PACKET_READ,MET_PACKET_WRITE,MET_COPY};
#define SWD_BATCH_OP_XFER_READ 2U
#define SWD_BATCH_STATUS_DONE 2U
#define SWD_BATCH_STATUS_ERROR 4U
#define SWD_BATCH_LAST_ACK(s) 1U
#define xil_printf(...) ((void)0)
static void dbg_pkt_flush(void){}
static void DAP_SWD_BatchClear(void){}
static unsigned DAP_SWD_BatchRun(void){return 2;}
static unsigned swd_read32(unsigned a){(void)a;return 0;}
static void swd_write32(unsigned a,unsigned b){(void)a;(void)b;}
static int swd_dma_upload(unsigned n){assert(n<=1024);return 0;}
static int swd_dma_download(unsigned first,unsigned n){(void)first;assert(n<=1024);for(unsigned i=0;i<n;i++)swd_dma_rsp[i]=0x12345678;return 0;}
static int swd_dma_download_to(unsigned first,unsigned n,uint32_t *p){(void)first;(void)n;(void)p;return -1;}
static int swd_abort_engines(void){return 0;}
static XTime dap_metric_start(void){return 0;}
static void dap_metric_end(unsigned a,XTime b,unsigned c){(void)a;(void)b;(void)c;}
static uint32_t DAP_SWD_TransferBlock_Legacy(const uint8_t *p,uint8_t *q){(void)p;(void)q;assert(0);return 0;}
''' + defs + '\n' + block + r'''
int main(void){
  uint8_t request[]={0,0,4,2}; /* 1024 DP reads, enters batch fallback. */
  uint8_t arena[4128];memset(arena,0xcc,sizeof arena);
  arena[0]=6;
  unsigned n=DAP_SWD_TransferBlock(request,arena+1);
  assert(n+1==4100 && arena[4096]!=0xcc && arena[4099]!=0xcc);
  printf("REPRO 1024-word read emits %u bytes into nominal 4096-byte response; guard[4096..4099]=%02x%02x%02x%02x\n",
         n+1,arena[4096],arena[4097],arena[4098],arena[4099]);
  return 0;
}
'''
results=[]
def compile_run(name, source, stuck=False):
    src=out/(name+'.c');src.write_text(source,encoding='utf-8')
    exe=out/(name+'.exe')
    p=subprocess.run([*cc,str(src),'-o',str(exe)],capture_output=True,text=True)
    (out/(name+'-compile.log')).write_text(p.stdout+p.stderr,encoding='utf-8')
    if p.returncode:raise RuntimeError(p.stderr)
    try:
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=2)
        if stuck:raise RuntimeError('Expected stuck busy was not observed')
        if p.returncode:raise RuntimeError(p.stdout+p.stderr)
        result=dict(name=name,output=p.stdout.strip())
    except subprocess.TimeoutExpired:
        if not stuck:raise
        result=dict(name=name,output='REPRO persistent BUSY ignores DAP_TransferAbort=1; host terminated after 2s')
    (out/(name+'.log')).write_text(result['output']+'\n',encoding='utf-8')
    results.append(result);print(result['output'])

compile_run('response_capacity',source)
sw=(root/'firmware/xusbps_daplink_dma/DAP/Source/SW_DP.c').read_text(encoding='utf-8')
sw=sw[sw.index('#endif\n\n\nuint8_t DAP_HOT_CODE SWD_Transfer'):]
body=function(sw,'uint8_t DAP_HOT_CODE SWD_Transfer(')
compile_run('scalar_busy',r'''
#include <stdint.h>
#include <stddef.h>
static volatile uint32_t registers[8];
volatile uint8_t DAP_TransferAbort=1;
#define SWD_BASE_ADDR ((uintptr_t)registers)
#define DAP_HOT_CODE
#define XFER_CMD_STS_REQUEST 8
#define XFER_CMD_STS_MODE 2
#define XFER_CMD_STS_START 1
#define DAP_TRANSFER_ERROR 8
void probe_target_observe(uint32_t a,uint32_t b,uint8_t c){(void)a;(void)b;(void)c;}
'''+body+r'''
int main(void){registers[1]=1;return SWD_Transfer(2,NULL);}
''',stuck=True)
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
