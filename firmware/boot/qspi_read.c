/* Read-only JTAG flash backup helper. No write-enable/erase/program opcodes. */
#include "xqspips.h"
#include "xparameters.h"
#include "xil_cache.h"
#include "xil_io.h"
#include <string.h>
static XQspiPs q;
/* SDK driver accesses whole FIFO words, including final padding. */
static unsigned char tx[4104] __attribute__((aligned(4)));
static unsigned char rx[4104] __attribute__((aligned(4)));
#define M ((volatile unsigned *)0x03ff0000U)
#define DATA ((unsigned char *)0x04000000U)
int main(void) {
    Xil_DCacheDisable();
    XQspiPs_Config *c = XQspiPs_LookupConfig(XPAR_XQSPIPS_0_DEVICE_ID);
    M[0] = 0;
    if (!c || XQspiPs_CfgInitialize(&q,c,c->BaseAddress)) {M[0]=0xdead0001; for(;;);}
    XQspiPs_SetOptions(&q, XQSPIPS_MANUAL_START_OPTION | XQSPIPS_FORCE_SSELECT_OPTION | XQSPIPS_HOLD_B_DRIVE_OPTION);
    XQspiPs_SetClkPrescaler(&q, XQSPIPS_CLK_PRESCALE_8);
    XQspiPs_SetSlaveSelect(&q);
    tx[0]=0x9f;
    if (XQspiPs_PolledTransfer(&q,tx,rx,4)) {M[0]=0xdead0002; for(;;);}
    M[1]=((unsigned)rx[1]<<16)|((unsigned)rx[2]<<8)|rx[3];
    tx[0]=5;
    if (XQspiPs_PolledTransfer(&q,tx,rx,2)) {M[0]=0xdead0003; for(;;);}
    M[2]=rx[1]; M[3]=0; M[4]=0; M[5]=0;
    unsigned capacity = M[1]==0xef4019 ? 0x02000000 : 0x01000000;
    M[0]=0x51535049;
    for (;;) {
        if (M[3]!=1) continue;
        unsigned start=M[4], length=M[5];
        if (start>=capacity || length>capacity-start) {M[3]=0xdead0004;continue;}
        unsigned pos=0;
        while(pos<length) {
            unsigned n=length-pos; if(n>4096)n=4096;
            unsigned a=start+pos;
            unsigned header=capacity>0x01000000?5:4;
            memset(tx,0,n+header);tx[0]=header==5?0x13:3;
            if(header==5)tx[1]=a>>24;
            tx[header-3]=a>>16;tx[header-2]=a>>8;tx[header-1]=a;
            if(XQspiPs_PolledTransfer(&q,tx,rx,n+header)){M[3]=0xdead0005;break;}
            memcpy(DATA+pos,rx+header,n);pos+=n;
        }
        __asm__ volatile("dsb sy" ::: "memory");
        if(pos==length) M[3]=2;
    }
}
