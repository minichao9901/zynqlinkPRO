.syntax unified
.cpu cortex-m3
.thumb
.section .text
.global itm_words
.thumb_func
itm_words:
    cpsid i
    ldr r0, =0xe0000000
    ldr r1, =0x20008200
    ldr r3, [r1]
    movs r4, #0
1:  ldr r5, [r0]
    tst r5, #1
    beq 1b
    str r4, [r0]
    adds r4, #1
    str r4, [r1, #4]
    cmp r4, r3
    blo 1b
2:  b 2b
