/* OCM runner for the isolated J7 stress fixture. The host supplies validated
 * DMI waveform frames, backups, and a bounded wall-time request. */
#include <stdint.h>

#define MMIO(addr) (*(volatile uint32_t *)(addr))
#define COMMAND ((volatile uint32_t *)0x0002ff40u)
#define PLAN ((const uint32_t *)0x03000000u)
#define CTRL MMIO(0x40000008u)
#define STATUS MMIO(0x40000004u)
#define TX ((volatile uint32_t *)0x40001000u)
#define RX ((volatile uint32_t *)0x40002000u)
#define GLOBAL ((volatile uint32_t *)0xf8f00200u)

enum {
    MAGIC, REQUEST, RESPONSE, DURATION, ERROR, FAIL_FRAME,
    READ_BYTES, WRITE_BYTES, COUNT, WORDS,
    ELAPSED_LO, ELAPSED_HI, READ_LO, READ_HI, WRITE_LO, WRITE_HI, BAD_LO, BAD_HI
};

static void sync(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
}

static uint64_t ticks(void)
{
    uint32_t low, high;
    do {
        high = GLOBAL[1];
        low = GLOBAL[0];
    } while (high != GLOBAL[1]);
    return ((uint64_t)high << 32) | low;
}

static void store64(unsigned index, uint64_t value)
{
    COMMAND[index] = (uint32_t)value;
    COMMAND[index + 1] = (uint32_t)(value >> 32);
}

static int wait_status(unsigned value)
{
    for (unsigned count = 0; count < 100000; ++count) {
        if ((STATUS & 31u) == value)
            return 1;
    }
    return 0;
}

static unsigned play(const uint32_t *words, unsigned length,
                     const uint32_t *checks, unsigned count, unsigned stride)
{
    if (!wait_status(5))
        return 2;
    for (unsigned i = 0; i < length; ++i)
        TX[i] = words[i];
    sync();
    CTRL = 1;
    if (!wait_status(15))
        return 3;
    unsigned error = 0;
    for (unsigned i = 0; i < count; ++i) {
        unsigned pos = checks[0];
        uint64_t actual = 0;
        unsigned previous_word = 512;
        uint32_t samples = 0;
        for (unsigned bit = 0; bit < 41; ++bit, pos += stride) {
            unsigned index = pos >> 3;
            if (index != previous_word) {
                samples = RX[index];
                previous_word = index;
            }
            if ((samples >> (pos & 7u)) & 1u)
                actual |= (uint64_t)1u << bit;
        }
        uint32_t low = (uint32_t)actual;
        uint32_t high = (uint32_t)(actual >> 32);
        if ((low & checks[1]) != checks[2] || (high & checks[3]) != checks[4]) {
            store64(BAD_LO, actual);
            error = 4;
            break;
        }
        checks += 5;
    }
    CTRL = 0;
    if (!wait_status(5))
        return 5;
    return error;
}

static unsigned run(unsigned seconds)
{
    uint32_t total_words = PLAN[0];
    uint32_t frames = PLAN[1];
    uint32_t stride = PLAN[2];
    if (total_words < 4 || total_words > 524288 || !frames || frames > 512 ||
        stride < 2 || stride > 8 || (stride & 1u) || !seconds || seconds > 120)
        return 1;
    const uint32_t *end = PLAN + total_words;
    GLOBAL[2] |= 1u;
    uint64_t start = ticks();
    uint64_t limit = (uint64_t)seconds * 333333333u;
    uint64_t duration[2] = {0, 0};
    unsigned error = 0;
    do {
        const uint32_t *frame = PLAN + 3;
        for (unsigned i = 0; i < frames; ++i) {
            if (end-frame < 4)
                return 1;
            unsigned length = frame[0];
            unsigned checks = frame[1];
            unsigned direction = frame[2];
            unsigned credit = frame[3];
            if (!length || length > 512 || !checks || checks > 4 || direction > 1 ||
                credit > 128 || end-frame < (int)(4+length+5*checks))
                return 1;
            const uint32_t *verification = frame + 4 + length;
            for (unsigned j = 0; j < checks; ++j) {
                if (verification[j*5] + 40*stride >= 8*length)
                    return 1;
            }

            uint64_t before = ticks();
            error = play(frame + 4, length, verification, checks, stride);
            duration[direction] += ticks() - before;
            if (error) {
                COMMAND[FAIL_FRAME] = i;
                break;
            }
            COMMAND[READ_BYTES + direction] += credit;
            COMMAND[COUNT]++;
            COMMAND[WORDS] += length;
            frame += 4 + length + 5*checks;
        }
        if (error)
            break;
        if (frame != end)
            return 1;
    } while (ticks() - start < limit);
    store64(ELAPSED_LO, ticks() - start);
    store64(READ_LO, duration[0]);
    store64(WRITE_LO, duration[1]);
    return error;
}

void stress_init(void)
{
    COMMAND[REQUEST] = 0;
    COMMAND[RESPONSE] = 0;
    GLOBAL[2] |= 1u;
    sync();
    COMMAND[MAGIC] = 0x4a535452u; /* JSTR */
}

void stress_poll(void)
{
    uint32_t id = COMMAND[REQUEST];
    if (id == COMMAND[RESPONSE])
        return;
    for (unsigned i = ERROR; i <= BAD_HI; ++i)
        COMMAND[i] = 0;
    uint32_t error = run(COMMAND[DURATION]);
    COMMAND[ERROR] = error;
    sync();
    COMMAND[RESPONSE] = id;
}
