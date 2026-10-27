.syntax unified
.cpu cortex-m3
.thumb
.section .text
.global producer
.thumb_func
producer:
    cpsid i
    ldr r0, =0x20000200
    ldr r1, =0x20001000
    movw r7, #8191
    movs r3, #0
    movs r4, #0
1:
    ldr r5, [r0, #40]
    adds r6, r3, #4
    ands r6, r6, r7
    cmp r6, r5
    beq 1b
    str r4, [r1, r3]
    dmb
    str r6, [r0, #36]
    adds r4, #1
    mov r3, r6
    str r4, [r0, #48]
    b 1b
