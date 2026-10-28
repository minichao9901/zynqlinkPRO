/* Standalone SWD fixture. PS GP0 writes AXI GPIO; no production DAP code. */
#include "xil_io.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include <stdint.h>
#define CTRL 0x40000000U
#define SENSE 0x40000008U
/* magic, command, half-period ns, ACK, data, parity, done, clock writes,
 * followed by {before-rise pad, after-rise pad} for 36 received bits. */
volatile uint32_t swd_diag[96] __attribute__((section(".dap_debug"),aligned(32)));
static uint32_t control_word=7;
static void pins(unsigned clock,unsigned data,unsigned release) {
 if(!(control_word&1U) && clock)swd_diag[7]++;
 control_word=(clock&1U)|((data&1U)<<1)|((release&1U)<<2);
 Xil_Out32(CTRL,control_word);__asm__ volatile("dsb sy" ::: "memory");
}
static unsigned pad(void) {return (Xil_In32(SENSE)>>1)&1U;}
static void delay(unsigned ns) {
 XTime start,now;XTime_GetTime(&start);
 uint64_t cycles=((uint64_t)COUNTS_PER_SECOND*ns+999999999U)/1000000000U;
 do {XTime_GetTime(&now);}while(now-start<cycles);
}
static void tick(unsigned data,unsigned release,unsigned ns) {
 pins(0,data,release);delay(ns);pins(1,data,release);delay(ns);
}
static void transfer(unsigned ns,unsigned header) {
 swd_diag[6]=0;swd_diag[7]=0;
 XTime begin,end;XTime_GetTime(&begin);
 pins(1,1,0);
 for(unsigned i=0;i<64;i++)tick(1,0,ns);
 for(unsigned i=0;i<16;i++)tick((0xe79eU>>i)&1U,0,ns);
 for(unsigned i=0;i<64;i++)tick(1,0,ns);
 for(unsigned i=0;i<8;i++)tick(0,0,ns);
 for(unsigned i=0;i<8;i++)tick((header>>i)&1U,0,ns);
 pins(1,1,1);tick(1,1,ns);
 uint32_t ack=0,data=0,parity=0;
 for(unsigned i=0;i<36;i++) {
  pins(0,1,1);delay(ns);unsigned lo=pad();
  pins(1,1,1);delay(ns);unsigned hi=pad();
  swd_diag[8+2*i]=lo;swd_diag[9+2*i]=hi;
  if(i<3)ack|=lo<<i;
  else if(i<35)data|=lo<<(i-3);
  else parity=lo;
 }
 tick(1,1,ns);pins(0,0,0);delay(ns);pins(1,0,0);delay(ns);
 pins(1,1,1);
 XTime_GetTime(&end);uint64_t elapsed=end-begin;
 swd_diag[80]=(uint32_t)elapsed;swd_diag[81]=(uint32_t)(elapsed>>32);
 swd_diag[82]=COUNTS_PER_SECOND;
 swd_diag[3]=ack;swd_diag[4]=data;swd_diag[5]=parity;
 __asm__ volatile("dsb sy" ::: "memory");swd_diag[6]=1;
}
int main(void) {
 Xil_DCacheDisable();
 Xil_Out32(GLOBAL_TMR_BASEADDR+GTIMER_CONTROL_OFFSET,1U);
 for(unsigned i=0;i<96;i++)swd_diag[i]=0;
 pins(1,1,1);swd_diag[2]=500000U;swd_diag[0]=0x53574431U;
 for(;;)if(swd_diag[1]) {
  unsigned ns=swd_diag[2];if(ns<100U)ns=100U;
  unsigned command=swd_diag[1];
  transfer(ns,command==2 ? 0x8dU : 0xa5U);swd_diag[1]=0;
 }
}
