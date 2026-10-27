.syntax unified
.cpu cortex-m3
.thumb
.global producer
.thumb_func
producer:
    ldr r0, =0x20004000
    movs r1, #0
1:  str r1, [r0]
    adds r1, #1
    b 1b
