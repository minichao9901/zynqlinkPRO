/* Temporary HPM6880 hart0 producer, no stack/Flash/PLL writes.
 * A noncached AHB ring carries consecutive little-endian u32, starting at zero.
 * Runtime publish size at STATE+72 defaults to 13 bytes, matching SEGGER text
 * writes and exercising unaligned producer/read offsets and the ring wrap.
 * Host saves ILM/AHB/GPR/CSR state and restores it after Web transport tests.
 */
.section .text
.option norvc
.global producer, _SEGGER_RTT, g_v
#ifdef HPM_USB_AXI_RING
.set _SEGGER_RTT, 0x01240000
.set g_v, 0x0124c000
#else
.set _SEGGER_RTT, 0xf0400200
.set g_v, 0xf0406000
#endif
producer:
    csrci mstatus, 8
    fence.i
    li t0, 0xf0400000
    li t1, 0x48504d50
    sw t1, 0(t0)
    li t1, _SEGGER_RTT
#ifdef HPM_USB_AXI_RING
    li t2, 0x012400b8
#else
    li t2, 0xf0401000
#endif
    li t3, 0
#ifdef HPM_USB_AXI_RING
    li t4, 32767
#else
    li t4, 16383
#endif
loop:
    lw t5, 64(t0)
    beqz t5, stopped
    sw zero, 68(t0)
    lw t5, 36(t1)
    lw t6, 40(t1)
    sub a0, t6, t5
    addi a0, a0, -1
    and a0, a0, t4
    lw a4, 72(t0)
    bltu a0, a4, heartbeat
    mv a1, a4
publish_byte:
    srli a0, t3, 2
    andi a2, t3, 3
    slli a2, a2, 3
    srl a0, a0, a2
    add a3, t2, t5
    sb a0, 0(a3)
    addi t3, t3, 1
    addi t5, t5, 1
    and t5, t5, t4
    addi a1, a1, -1
    bnez a1, publish_byte
    fence rw,w
    sw t5, 36(t1)
    sw t3, 24(t0)
    j heartbeat
stopped:
    li t5, 1
    sw t5, 68(t0)
    li t3, 0
heartbeat:
    lw t5, 16(t0)
    addi t5, t5, 1
    sw t5, 16(t0)
    csrr t5, mcycle
    sw t5, 20(t0)
    j loop
