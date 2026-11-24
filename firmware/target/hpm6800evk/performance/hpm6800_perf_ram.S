/* HPM6880 hart0 temporary ILM producer. No stack, PLL, pinmux or Flash writes.
 * Host saves/restores ILM, AHB SRAM, GPRs, dpc/dcsr/mstatus. AHB SRAM is the
 * noncached RTT ring. Monotonic u32 values and stop ACK permit exact accounting.
 */
.section .text
.option norvc
.global producer
producer:
    csrci mstatus, 8
    fence.i
    li t0, 0xf0400000
    li t1, 0x48504d50
    sw t1, 0(t0)
    li t1, 0xf0400200
    li t2, 0xf0401000
    li t3, 0
    li t4, 8191
loop:
    lw t5, 64(t0)
    beqz t5, stopped
    sw zero, 68(t0)
    lw t5, 36(t1)
    addi t6, t5, 4
    and t6, t6, t4
    lw a0, 40(t1)
    beq t6, a0, heartbeat
    add a0, t2, t5
    sw t3, 0(a0)
    addi t3, t3, 1
    fence rw,w
    sw t6, 36(t1)
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
