.syntax unified
.cpu cortex-m3
.thumb

.section .vectors, "a", %progbits
.word 0x2000f000
.word trace_loop
.rept 62
.word trace_trap
.endr

.section .text, "ax", %progbits
.global trace_loop
.type trace_loop,%function
.thumb_func
trace_loop:
    movw r4, #0x1234
    movw r5, #0x5678
1:
    bl trace_mix
    tst r4, #1
    beq 2f
    eor.w r5, r5, r4, ror #5
    b 1b
2:
    adds r5, #17
    b 1b
.size trace_loop,.-trace_loop

.global trace_mix
.type trace_mix,%function
.thumb_func
trace_mix:
    adds r4, #1
    eors r4, r5
    ror.w r4, r4, #7
    bx lr
.size trace_mix,.-trace_mix

.type trace_trap,%function
.thumb_func
trace_trap:
    b trace_trap
.size trace_trap,.-trace_trap

.section .bss, "aw", %nobits
.align 2
.global g_sysclk_hz, g_clock_err
g_sysclk_hz: .space 4
g_clock_err: .space 4
