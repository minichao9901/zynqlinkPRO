.syntax unified
.cpu cortex-a9
.arm
.section .text.start, "ax"
.global _start
_start:
    cpsid if
    ldr sp, =0x2e000
    bl swd200_main
1:  b 1b
