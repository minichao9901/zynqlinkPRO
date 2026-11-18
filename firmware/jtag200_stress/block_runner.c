/* Probe-local batching benchmark for the pure JTAG pipeline.
 * Both host-supplied patterns and all stats live in Zynq RAM. The PL
 * checks the target ILM bounds before it accepts a descriptor. */
#include <stdint.h>

#define REG(addr) (*(volatile uint32_t *)(addr))
#define GTC ((volatile uint32_t *)0xf8f00200u)
#define REQUEST ((volatile uint32_t *)0x0002ff40u)
#define PATTERN ((const uint32_t *)0x03000000u)
#define TX ((volatile uint32_t *)0x40001000u)
#define RX ((volatile uint32_t *)0x40002000u)
#define CTRL REG(0x40000008u)
#define STATUS REG(0x40000004u)
#define RES REG(0x40000020u)
#define COUNT 256u
#define BUFFER_BYTES (COUNT * 4u)

enum {
    MAGIC, SEQ, RESPONSE, DURATION, ERROR, DIRECTION, READ_BYTES, WRITE_BYTES,
    BITS, SEGMENTS, ELAPSED_LO, ELAPSED_HI, READ_LO, READ_HI, WRITE_LO, WRITE_HI,
    HEADER, BAD_WORD, BAD_VALUE, DMI_BUSY, DMI_OTHER
};

static void barrier(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
}

static uint64_t ticks(void)
{
    uint32_t high, low;
    do {
        high = GTC[1];
        low = GTC[0];
    } while (high != GTC[1]);
    return ((uint64_t)high << 32) | low;
}

static void save64(unsigned field, uint64_t value)
{
    REQUEST[field] = (uint32_t)value;
    REQUEST[field + 1] = (uint32_t)(value >> 32);
}

static int wait_status(unsigned expected)
{
    for (unsigned n = 0; n < 150000; ++n)
        if ((STATUS & 31u) == expected)
            return 1;
    return 0;
}

static unsigned transfer(int write, uint32_t inversion)
{
    if (!wait_status(5))
        return 2;
    if (write)
        for (unsigned i = 0; i < COUNT; ++i)
            TX[i+1] = PATTERN[i] ^ inversion;
    barrier();
    CTRL = write ? 13 : 5;
    if (!wait_status(15))
        return 3;
    unsigned error = 0;
    REQUEST[BITS] = REG(0x40000024u);
    REQUEST[SEGMENTS] = REG(0x40000028u);
    REQUEST[DMI_BUSY] = REG(0x4000002cu);
    REQUEST[DMI_OTHER] = REG(0x40000030u);
    if (RES != 1) {
        REQUEST[HEADER] = RES;
        error = 4;
    } else {
        REQUEST[HEADER] = RX[0];
        if (REQUEST[HEADER] != (0x00010000u | COUNT))
            error = 5;
    }
    if (!error && !write) {
        for (unsigned i = 0; i < COUNT; ++i) {
            uint32_t result = RX[i+1];
            if (result != (PATTERN[i] ^ inversion)) {
                REQUEST[BAD_WORD] = i;
                REQUEST[BAD_VALUE] = result;
                error = 6;
                break;
            }
        }
    }
    CTRL = 0;
    if (!wait_status(5))
        return 7;
    return error;
}

static unsigned exercise(unsigned seconds, unsigned direction)
{
    if (seconds > 120 || direction > 2 || REG(0x40000010u) != 0x50495045u ||
        REG(0x40000014u) != 0x0105f000u || REG(0x40000018u) != COUNT)
        return 1;
    unsigned error;
    unsigned completed = 0;
    uint64_t read_time = 0, write_time = 0;
    uint64_t start = ticks();
    uint64_t duration = (uint64_t)seconds * 333333333u;
    do {
        uint64_t before;
        uint32_t inversion = completed & 1u ? UINT32_MAX : 0;
        if (direction != 1) {
            before = ticks();
            error = transfer(1, inversion);
            write_time += ticks() - before;
            if (error)
                break;
            REQUEST[WRITE_BYTES] += BUFFER_BYTES;
        }
        if (direction != 2) {
            before = ticks();
            error = transfer(0, direction == 1 ? 0 : inversion);
            read_time += ticks() - before;
            if (error)
                break;
            REQUEST[READ_BYTES] += BUFFER_BYTES;
        }
        completed++;
    } while (ticks() - start < duration);
    save64(ELAPSED_LO, ticks() - start);
    save64(READ_LO, read_time);
    save64(WRITE_LO, write_time);
    return error;
}

void stress_init(void)
{
    REQUEST[SEQ] = 0;
    REQUEST[RESPONSE] = 0;
    GTC[2] |= 1u;
    barrier();
    REQUEST[MAGIC] = 0x4a424c4bu; /* JBLK */
}

void stress_poll(void)
{
    unsigned seq = REQUEST[SEQ];
    if (seq == REQUEST[RESPONSE])
        return;
    for (unsigned i=READ_BYTES; i<=DMI_OTHER; ++i)
        REQUEST[i] = 0;
    REQUEST[ERROR] = exercise(REQUEST[DURATION], REQUEST[DIRECTION]);
    barrier();
    REQUEST[RESPONSE] = seq;
}
