.syntax unified
.cpu cortex-m3
.thumb
.section .text
.global echo
.thumb_func
echo:
    cpsid i
    ldr r0, =0x40010808
    ldr r1, =0x40010c10
    ldr r2, =0xe0001004
    ldr r3, =0x20008200
    movw r7, #417
    movs r4, #8
    str r4, [r1]
    movs r4, #0
    str r4, [r3]
    str r4, [r3, #4]
    ldr r4, =0x4543484f
    str r4, [r3, #8]
1:  ldr r4, [r0]
    tst.w r4, #0x8000
    beq 1b
2:  ldr r4, [r0]
    tst.w r4, #0x8000
    bne 2b
    ldr r8, [r2]
    movw r9, #625
    add r8, r9
    movs r4, #0
    movs r5, #1
    movs r6, #8
3:  ldr r9, [r2]
    subs.w r9, r9, r8
    bmi 3b
    ldr r9, [r0]
    tst.w r9, #0x8000
    it ne
    orrne r4, r5
    lsls r5, #1
    add r8, r7
    subs r6, #1
    bne 3b
4:  ldr r9, [r2]
    subs.w r9, r9, r8
    bmi 4b
    ldr r9, [r0]
    tst.w r9, #0x8000
    bne 5f
    ldr r9, [r3, #4]
    add r9, #1
    str r9, [r3, #4]
    b 1b
5:  str r4, [r3, #12]
    eor r4, r4, #0xa5
    lsls r4, #1
    orr r4, r4, #0x200
    movs r6, #10
    ldr r8, [r2]
6:  tst r4, #1
    ite ne
    movne r9, #8
    moveq.w r9, #0x80000
    str r9, [r1]
    add r8, r7
7:  ldr r9, [r2]
    subs.w r9, r9, r8
    bmi 7b
    lsrs r4, #1
    subs r6, #1
    bne 6b
    ldr r9, [r3]
    add r9, #1
    str r9, [r3]
    b 1b
