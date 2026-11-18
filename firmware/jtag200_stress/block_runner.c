/* Probe-local batching benchmark for the pure JTAG pipeline.
 * Both host-supplied patterns and all stats live in Zynq RAM. The PL
 * checks the target scratch RAM bounds before it accepts a descriptor. */
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
    HEADER, BAD_WORD, BAD_VALUE, DMI_BUSY, DMI_OTHER, DIAGNOSTICS,
    PROFILE_ID = DIAGNOSTICS + 8,
    READ_SCAN = PROFILE_ID + 1, READ_COMPARE = READ_SCAN + 2,
    WRITE_SCAN = READ_COMPARE + 2, WRITE_STAGE = WRITE_SCAN + 2
};

struct transfer_time {
    uint64_t scan, payload;
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

static unsigned transfer(int write, uint32_t inversion, int resident, struct transfer_time *time)
{
    if (!wait_status(5))
        return 2;
    if (write && !resident) {
        uint64_t stage = ticks();
        for (unsigned i = 0; i < COUNT; ++i)
            TX[i+1] = PATTERN[i] ^ inversion;
        time->payload += ticks() - stage;
    }
    barrier();
    uint64_t scan = ticks();
    CTRL = (write ? 13u : 5u) | (resident && inversion ? 16u : 0u);
    if (!wait_status(15))
        return 3;
    time->scan += ticks() - scan;
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
    if (!error && !write && !resident) {
        uint64_t compare = ticks();
        for (unsigned i = 0; i < COUNT; ++i) {
            uint32_t result = RX[i+1];
            if (result != (PATTERN[i] ^ inversion)) {
                REQUEST[BAD_WORD] = i;
                REQUEST[BAD_VALUE] = result;
                error = 6;
                break;
            }
        }
        time->payload += ticks() - compare;
    }
    if (error || REQUEST[DURATION] == 0)
        for (unsigned i = 0; i < 8; ++i)
            REQUEST[DIAGNOSTICS+i] = RX[504+i];
    CTRL = 0;
    if (!wait_status(5))
        return 7;
    return error;
}

static unsigned exercise(unsigned seconds, unsigned direction)
{
    uint32_t timing = REG(0x4000001cu);
    uint32_t base = timing & (1u << 21) ? 0x24050000u : 0x0105f000u;
    if (seconds > 120 || direction > 2 || REG(0x40000010u) != 0x50495045u ||
        REG(0x40000014u) != base || REG(0x40000018u) != COUNT)
        return 1;
    int resident = (timing & (1u << 23)) != 0;
    if (resident) {
        if (!wait_status(5))
            return 2;
        for (unsigned i = 0; i < COUNT; ++i)
            TX[i+1] = PATTERN[i];
        barrier();
    }
    unsigned error;
    unsigned completed = 0;
    uint64_t read_time = 0, write_time = 0;
    struct transfer_time read = {0, 0}, write = {0, 0};
    uint64_t start = ticks();
    uint64_t duration = (uint64_t)seconds * 333333333u;
    do {
        uint64_t before;
        uint32_t inversion = completed & 1u ? UINT32_MAX : 0;
        if (direction != 1) {
            before = ticks();
            error = transfer(1, inversion, resident, &write);
            write_time += ticks() - before;
            if (error)
                break;
            REQUEST[WRITE_BYTES] += BUFFER_BYTES;
        }
        if (direction != 2) {
            before = ticks();
            error = transfer(0, direction == 1 ? 0 : inversion, resident, &read);
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
    save64(READ_SCAN, read.scan);
    save64(READ_COMPARE, read.payload);
    save64(WRITE_SCAN, write.scan);
    save64(WRITE_STAGE, write.payload);
    return error;
}

void stress_init(void)
{
    REQUEST[SEQ] = 0;
    REQUEST[RESPONSE] = 0;
    REQUEST[PROFILE_ID] = 0x54494d45u; /* TIME */
    GTC[2] |= 1u;
    barrier();
    REQUEST[MAGIC] = 0x4a424c4bu; /* JBLK */
}

void stress_poll(void)
{
    unsigned seq = REQUEST[SEQ];
    if (seq == REQUEST[RESPONSE])
        return;
    for (unsigned i=READ_BYTES; i<DIAGNOSTICS+8; ++i)
        REQUEST[i] = 0;
    for (unsigned i=READ_SCAN; i<WRITE_STAGE+2; ++i)
        REQUEST[i] = 0;
    REQUEST[ERROR] = exercise(REQUEST[DURATION], REQUEST[DIRECTION]);
    barrier();
    REQUEST[RESPONSE] = seq;
}
