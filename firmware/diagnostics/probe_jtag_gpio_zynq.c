/* Temporary Zynq PS firmware. Existing PL GPIO mux is left in SWD mode.
 * B19 is driven through AXI GPIO bit0; A20 is sampled through bit1. */
#include "xil_io.h"
#include "xil_cache.h"
#include "sleep.h"
#include <stdint.h>
#define GPIO_DATA 0x40000000U
#define GPIO_TRI 0x40000004U
#define ROUTE 0x40010080U
#define PINS 0x40010094U
volatile uint32_t io_result[64] __attribute__((section(".dap_debug"),aligned(32)));
static void drive(unsigned mode,unsigned v) {
    if(mode)Xil_Out32(PINS,0x103U|((v&1U)<<2));
    else Xil_Out32(GPIO_DATA,0xcU|(v&1U));
}
int main(void) {
    Xil_DCacheDisable();
    for(unsigned i=0;i<64;i++)io_result[i]=0;
    io_result[0]=0x494f5a31U;
    io_result[12]=Xil_In32(GPIO_TRI);io_result[13]=Xil_In32(ROUTE);
    Xil_Out32(ROUTE,2U);Xil_Out32(PINS,0U);
    drive(0,0);Xil_Out32(GPIO_TRI,0xaU); /* bit1 TDO input, bit2 reset released. */
    usleep(100000);
    const unsigned waits[3]={1000,100,10};
    const unsigned loops[3]={100,1000,10000};
    for(unsigned phase=0;phase<6;phase++) {
        unsigned mode=phase/3;
        Xil_Out32(ROUTE,mode ? 3U : 2U);
        unsigned errors=0;
        for(unsigned i=0;i<loops[phase%3];i++)for(unsigned v=0;v<2;v++) {
            drive(mode,v);usleep(waits[phase%3]);
            unsigned levels=Xil_In32(PINS);
            unsigned actual=(levels>>3)&1U;
            if(((levels>>2)&1U)!=v)io_result[11]++;
            io_result[2]++;io_result[4+v]++;
            if(actual!=(v^1U)) {
                if(io_result[3]==0) {io_result[6]=phase;io_result[7]=i;io_result[8]=v;io_result[9]=actual;}
                io_result[3]++;errors++;
            }
        }
        io_result[16+phase*4]=waits[phase%3];io_result[17+phase*4]=loops[phase%3]*2;
        io_result[18+phase*4]=errors;
    }
    drive(1,0);usleep(1000);io_result[10]=Xil_In32(PINS);
    Xil_Out32(PINS,0U);Xil_Out32(ROUTE,2U);Xil_Out32(GPIO_TRI,0xbU);
    io_result[1]=1;
    for(;;)__asm__ volatile("nop");
}
