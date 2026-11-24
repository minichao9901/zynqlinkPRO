#include <stdint.h>

extern uint32_t _estack, _sdata, _edata, _sidata, _sbss, _ebss;
int main(void);
void Reset_Handler(void);
void Default_Handler(void);
void SysTick_Handler(void) __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void) __attribute__((weak, alias("Default_Handler")));

volatile uint32_t g_fault_status, g_fault_detail;

void Default_Handler(void)
{
    g_fault_status = *(volatile uint32_t *)0xe000ed28u;
    g_fault_detail = *(volatile uint32_t *)0xe000ed2cu;
    for (;;) {}
}

__attribute__((section(".vectors"), used))
void (*const vectors[])(void) = {
    (void (*)(void))&_estack, Reset_Handler, Default_Handler, Default_Handler,
    Default_Handler, Default_Handler, Default_Handler, 0, 0, 0, 0,
    Default_Handler, Default_Handler, 0, PendSV_Handler, SysTick_Handler,
};

void Reset_Handler(void)
{
    __asm__ volatile ("cpsid i" ::: "memory");
    *(volatile uint32_t *)0xe000e010u = 0; /* SysTick CTRL */
    *(volatile uint32_t *)0xe000ed04u = (1u << 25) | (1u << 27);
    unsigned bank_count = (*(volatile uint32_t *)0xe000e004u & 15u) + 1u;
    for (unsigned bank = 0; bank < bank_count; ++bank) {
        ((volatile uint32_t *)0xe000e180u)[bank] = UINT32_MAX; /* NVIC ICER */
        ((volatile uint32_t *)0xe000e280u)[bank] = UINT32_MAX; /* NVIC ICPR */
    }
    *(volatile uintptr_t *)0xe000ed08u = (uintptr_t)vectors;
#ifdef TARGET_H743
    *(volatile uint32_t *)0xe000ed88u |= 0xfu << 20;
    volatile uint32_t *const fpccr = (volatile uint32_t *)0xe000ef34u;
    *fpccr = (*fpccr | (1u << 31)) & ~(1u << 30);
#endif
    __asm__ volatile ("dsb; isb" ::: "memory");
    const uint32_t *source = &_sidata;
    for (uint32_t *dest = &_sdata; dest < &_edata; ++dest)
        *dest = *source++;
    for (uint32_t *dest = &_sbss; dest < &_ebss; ++dest)
        *dest = 0;
    __asm__ volatile ("cpsie i" ::: "memory");
    main();
    for (;;) {}
}
