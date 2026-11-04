.syntax unified
.cpu cortex-m3
.thumb
.section .text
.global fault_entry
.thumb_func
fault_entry:
    udf #0
1:  b 1b
.balign 64
.global fault_handler
.thumb_func
fault_handler:
    ldr r0, =0x20002300
    movs r1, #1
    str r1, [r0]
2:  ldr r1, [r0, #4]
    cmp r1, #0
    beq 2b
    // Skip the intentional 16-bit UDF in the hardware exception frame.
    ldr r1, [sp, #24]
    adds r1, #2
    str r1, [sp, #24]
    bx lr
.pool
