.syntax unified
.cpu cortex-m3
.thumb
.ifndef FIXTURE_BASE
.equ FIXTURE_BASE, 0x20000000
.endif
.global producer
.thumb_func
producer:
    ldr r0, =FIXTURE_BASE + 0x4000
    movs r1, #0
1:  str r1, [r0]
    adds r1, #1
    b 1b
