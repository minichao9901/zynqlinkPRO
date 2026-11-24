.syntax unified
.cpu cortex-m3
.thumb
.text
.global spi_source
.thumb_func
/* F103ZE fixture for the existing J7 cable: PA13=CS, PA14=SCK, PA15=MOSI.
 * The host arms the receiver before the timed SWJ-to-GPIO handoff.
 * Every exit restores GPIO and SWJ before parking in SRAM. */
spi_source:
    cpsid i
    ldr r9, =0x20008200
    ldmia r9, {r0,r1}       /* mode, byte count */
    ldr r2, =0xe0001004     /* DWT CYCCNT */
    ldr r3, [r2]
    ldr r4, =96000000       /* two seconds at CDC48 HCLK */
1:  ldr r5, [r2]
    subs r5, r5, r3
    cmp r5, r4
    blo 1b

    ldr r10, =0x40021018   /* RCC APB2ENR */
    ldr r4, [r10]
    orr r5, r4, #5
    str r5, [r10]
    ldr r5, [r10]
    ldr r11, =0x40010804   /* GPIOA CRH */
    ldr r5, [r11]
    ldr r6, [r11, #8]      /* GPIOA ODR */
    ldr r12, =0x40010004   /* AFIO MAPR */
    ldr r7, [r12]
    bic r7, r7, #0x07000000
                           /* The enclosing F103 guard enabled full SWJ. */
    str r4, [r9,#16]
    str r5, [r9,#20]
    str r6, [r9,#24]
    str r7, [r9,#28]

    ldr r8, =0xfff00000
    bic r5, r5, r8
    ldr r8, =0x33300000
    orr r5, r5, r8
    bic r6, r6, #0xe000
    tst r0, #2
    it ne
    orrne r6, r6, #0x4000
    orr r4, r6, #0x2000
    str r4, [r11, #8]
    str r5, [r11]
    bic r5, r7, #0x07000000
    orr r5, r5, #0x04000000
    str r5, [r12]
    nop
    nop
    str r6, [r11,#8]       /* Assert CS, park SCK */
    ldr lr, [r2]
    movs r3, #0            /* Byte index */
2:  eor r4, r3, r3, lsr #3
    and r4, r4, #255
    lsl r4, r4, #24        /* Byte ramp xor index>>3, MSB first */
    movs r2, #8
3:  bic r5, r6, #0x8000
    lsls r4, r4, #1
    it cs
    orrcs r5, r5, #0x8000
    tst r0, #1
    bne 4f
    str r5, [r11,#8]       /* CPHA=0: data before leading edge */
    eor r8, r5, #0x4000
    str r8, [r11,#8]
    nop
    str r5, [r11,#8]
    b 5f
4:  eor r8, r5, #0x4000   /* CPHA=1: data on leading edge */
    str r8, [r11,#8]
    nop
    nop
    str r5, [r11,#8]       /* Trailing edge samples */
5:  subs r2, r2, #1
    bne 3b
    adds r3, r3, #1
    cmp r3, r1
    blo 2b
    orr r4, r6, #0x2000
    str r4, [r11,#8]
    ldr r2, =0xe0001004
    ldr r4, [r2]
    subs r4, r4, lr
    str r4, [r9,#12]
    nop
    nop
    str r7, [r12]          /* SWD supplies the idle pulls while GPIO is restored */
    ldr r5, [r9,#20]
    str r5, [r11]
    ldr r6, [r9,#24]
    str r6, [r11,#8]
    ldr r4, [r9,#16]
    str r4, [r10]
    ldr r4, =0x53504944    /* SPID */
    str r4, [r9,#8]
6:  b 6b
.ltorg
