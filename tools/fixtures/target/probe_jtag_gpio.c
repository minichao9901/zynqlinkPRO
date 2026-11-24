/* SRAM-only F103CB fixture. PA15 input -> inverted PB3 output; SWD stays on.
 * The host saves/restores all SRAM and core registers. Setting mailbox[2]
 * requests a graceful GPIO restore before the host halts this fixture. */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define RCC REG(0x40021018U)
#define MAPR REG(0x40010004U)
#define A_CRH REG(0x40010804U)
#define A_IDR REG(0x40010808U)
#define B_CRL REG(0x40010c00U)
#define B_ODR REG(0x40010c0cU)
#define B_BSRR REG(0x40010c10U)

__attribute__((noreturn)) void probe_io_target(void) {
    volatile uint32_t *m=(volatile uint32_t *)0x20004000U;
    uint32_t rcc=RCC;
    RCC=rcc|0xdU; /* AFIO, GPIOA, GPIOB clocks; no system clock changes. */
    uint32_t mapr=MAPR,acrh=A_CRH,bcrl=B_CRL,bodr=B_ODR;
    m[12]=rcc;m[13]=mapr;m[14]=acrh;m[15]=bcrl;m[16]=bodr;
    MAPR=(mapr&~0x07000000U)|0x02000000U; /* JTAG off, SWD on. */
    A_CRH=(acrh&0x0fffffffU)|0x40000000U; /* PA15 floating input. */
    B_BSRR=8U; /* Preload high before enabling PB3 output. */
    B_CRL=(bcrl&~0x0000f000U)|0x00003000U; /* PB3 push-pull 50 MHz. */
    uint32_t last=(A_IDR>>15)&1U;
    m[0]=0x494f4631U;m[1]=1;
    while(!m[2]) {
        uint32_t v=(A_IDR>>15)&1U;
        B_BSRR=v ? (8U<<16) : 8U;
        m[4]++;m[5+v]++;m[10]=v;m[11]=v^1U;
        if(v!=last) {m[7]++;m[8+(!v)]++;last=v;}
    }
    B_ODR=bodr;B_CRL=bcrl;A_CRH=acrh;MAPR=mapr;RCC=rcc;
    m[1]=2;
    for(;;)__asm__ volatile("nop");
}
