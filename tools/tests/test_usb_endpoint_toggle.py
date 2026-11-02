"""Execute the actual Chapter9 CLEAR_FEATURE branch with USB PID semantics."""
from pathlib import Path
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]

class EndpointToggleTests(unittest.TestCase):
    def test_clear_halt_resynchronizes_both_directions_even_without_a_stall(self):
        source=(ROOT/'firmware/xusbps_daplink_dma/xusbps_ch9.c').read_text()
        branch=source.split('case XUSBPS_REQ_CLEAR_FEATURE:',1)[1].split('case XUSBPS_REQ_SET_FEATURE:',1)[0]
        harness=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#define XUSBPS_STATUS_MASK 3
#define XUSBPS_STATUS_ENDPOINT 2
#define XUSBPS_ENDPOINT_HALT 0
#define XUSBPS_EPCRn_OFFSET(n) (n)
#define XUSBPS_EPCR_TXS_MASK (1u<<16)
#define XUSBPS_EPCR_RXS_MASK 1u
#define XUSBPS_EPCR_TXR_MASK (1u<<22)
#define XUSBPS_EPCR_RXR_MASK (1u<<6)
typedef struct {unsigned regs[8],pid[8][2],acks;} XUsbPs;
typedef struct {unsigned bmRequestType,wValue,wIndex;} Setup;
static void XUsbPs_ClrBits(XUsbPs *p,unsigned n,unsigned bits){assert(n<8);p->regs[n]&=~bits;}
static void XUsbPs_SetBits(XUsbPs *p,unsigned n,unsigned bits){assert(n<8);p->regs[n]|=bits;
 if(bits&XUSBPS_EPCR_TXR_MASK)p->pid[n][1]=0;
 if(bits&XUSBPS_EPCR_RXR_MASK)p->pid[n][0]=0;
}
static void XUsbPs_EpBufferSend(XUsbPs *p,unsigned ep,void *v,unsigned n){assert(!ep&&!v&&!n);p->acks++;}
static void request(XUsbPs *InstancePtr,Setup *SetupData){int Error=0;switch(1){case 1:BRANCH}assert(!Error);}
int main(void){
 for(unsigned ep=1;ep<8;ep++)for(unsigned in=0;in<2;in++)for(unsigned stalled=0;stalled<2;stalled++){
  XUsbPs p={0};Setup setup={2,0,ep|(in?128:0)};
  unsigned mask=in?XUSBPS_EPCR_TXS_MASK:XUSBPS_EPCR_RXS_MASK;
  p.regs[ep]=0x00880088|(stalled?mask:0);p.pid[ep][0]=p.pid[ep][1]=1;
  request(&p,&setup);
  assert(p.acks==1&&p.pid[ep][in]==0&&p.pid[ep][!in]==1);
  assert(!(p.regs[ep]&mask));assert((p.regs[ep]&0x00880088)==0x00880088);
  /* Host CLEAR_FEATURE expects DATA0: the next DEF must be accepted. */
  assert(p.pid[ep][in]==0);
 }
 puts("Chapter9 IN/OUT HALT clear: DATA0 restored with/without STALL; peer direction preserved");
}
'''.replace('BRANCH',branch)
        with tempfile.TemporaryDirectory() as td:
            c=Path(td)/'toggle.c';exe=Path(td)/'toggle.exe';c.write_text(harness)
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-O2',str(c),'-o',str(exe)],check=True,capture_output=True)
            subprocess.run([str(exe)],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
