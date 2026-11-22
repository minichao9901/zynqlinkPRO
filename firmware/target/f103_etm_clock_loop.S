.syntax unified
.cpu cortex-m3
.thumb

.section .vectors,"a"
.word 0x20000400
.word trace_entry
.rept 74
.word trace_trap
.endr

.text
.global trace_entry
.thumb_func
trace_entry:
    cpsid i
    ldr r1, =loop_count
    movs r0, #0
    ldr r4, =trace_even
    ldr r5, =trace_odd
    b trace_loop
.size trace_entry, .-trace_entry
.global trace_loop
.thumb_func
trace_loop:
    adds r0, #1
    tst r0, #1
    bne 1f
    blx r4
    b 2f
1:  blx r5
2:
    str r0, [r1]
    b trace_loop
.size trace_loop, .-trace_loop
.global trace_even
.thumb_func
trace_even:
    eors r2, r0
    bx lr
.size trace_even, .-trace_even
.global trace_odd
.thumb_func
trace_odd:
    adds r2, r0
    bx lr
.size trace_odd, .-trace_odd
.thumb_func
trace_trap:
    b trace_trap
.size trace_trap, .-trace_trap
.ltorg

.bss
.balign 4
.global loop_count, g_sysclk_hz, g_clock_err
loop_count: .space 4
g_sysclk_hz: .space 4
g_clock_err: .space 4
