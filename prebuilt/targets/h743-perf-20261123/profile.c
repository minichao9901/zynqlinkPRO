#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define BASE 0x58024400u
#define MAILBOX ((volatile uint32_t *)0x24071000u)
__attribute__((noreturn,used,section(".text.start")))
void h743_perf_entry(void) {
    uint32_t n=0;
    uint32_t last=0xffffffff;
    for (;;) {
      uint32_t current=REG(BASE+0x10);
      if(current!=last){last=current;
    MAILBOX[1]=REG(BASE+0x10);
    MAILBOX[2]=REG(BASE+0x18);
    MAILBOX[3]=REG(BASE+0x1c);
    MAILBOX[4]=REG(BASE+0x20);
    MAILBOX[5]=REG(BASE+0x28);
    MAILBOX[6]=REG(BASE+0x30);
    MAILBOX[7]=REG(0x58024818u);
    MAILBOX[0]=0x48373433u;
      }
        MAILBOX[8]=++n;
        MAILBOX[9]=REG(0xe0001004u);
        for (volatile unsigned i=0; i<8192; ++i) __asm__ volatile("nop");
    }
}
