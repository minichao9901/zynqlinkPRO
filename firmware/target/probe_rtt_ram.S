.syntax unified
.cpu cortex-m3
.thumb
.ifndef FIXTURE_BASE
.equ FIXTURE_BASE, 0x20000000
.endif
.ifndef RTT_RING_OFFSET
.equ RTT_RING_OFFSET, 0x1000
.endif
.ifndef RTT_RING_MASK
.equ RTT_RING_MASK, 8191
.endif
.section .text
.global producer
.thumb_func
producer:
    cpsid i
    ldr r0, =FIXTURE_BASE + 0x200
    ldr r1, =FIXTURE_BASE + RTT_RING_OFFSET
    movw r7, #RTT_RING_MASK
    movs r3, #0
    movs r4, #0
1:
    ldr r5, [r0, #40]
    /* Host consumers release bytes, including partial words. Compare free
     * byte count so an unaligned RdOff cannot allow the writer to lap it. */
    subs r6, r5, r3
    subs r6, r6, #1
    ands r6, r6, r7
    cmp r6, #4
    blo 1b
    adds r6, r3, #4
    ands r6, r6, r7
    str r4, [r1, r3]
    dmb
    str r6, [r0, #36]
    adds r4, #1
    mov r3, r6
    str r4, [r0, #48]
    b 1b
