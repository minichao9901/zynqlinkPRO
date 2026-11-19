#include <stdint.h>

#define MMIO(addr) (*(volatile uint32_t *)(addr))
#define MAILBOX ((volatile uint32_t *)0x0002ff00u)
#define SWD_ID     MMIO(0x40000000u)
#define SWD_STATUS MMIO(0x40000004u)
#define SWD_HOLD   MMIO(0x40000008u)
#define SWD_TIMING MMIO(0x4000000cu)
#define SWD_TAP    MMIO(0x40000018u)
#define FCLK1_CTRL MMIO(0xf8000180u)

enum { SIGNATURE = 0x53323030u, READY = 1u, CLOCK_HELD = 16u, IDLE = 32u };
enum { MAGIC, REQUEST, PROFILE, TIMING, TAP, RESPONSE, ERROR, CLOCK_CTRL, SWCLK_HZ };

struct profile {
    uint32_t divisor;
    uint32_t rate;
    uint32_t swclk_hz;
};

static const struct profile profiles[] = {
    {32, 0,  50000000},
    {32, 1, 100000000},
    {40, 2, 160000000},
    {32, 2, 200000000},
#ifdef SWD200_BOARD_BENCH
    {48, 1, 66666667},
#define FULL_RATE(d) {d, 2, (6400000000ull + (d)/2) / (d)}
    FULL_RATE(53), FULL_RATE(52), FULL_RATE(51), FULL_RATE(50), FULL_RATE(49),
    FULL_RATE(48), FULL_RATE(47), FULL_RATE(46), FULL_RATE(45), FULL_RATE(44),
    FULL_RATE(43), FULL_RATE(42), FULL_RATE(41), FULL_RATE(40), FULL_RATE(39),
    FULL_RATE(38), FULL_RATE(37), FULL_RATE(36), FULL_RATE(35), FULL_RATE(34), FULL_RATE(33),
#undef FULL_RATE
#endif
};

static void barrier(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
}

static int wait_status(uint32_t mask, uint32_t value)
{
    for (unsigned attempt = 0; attempt < 100000; ++attempt) {
        if ((SWD_STATUS & mask) == value)
            return 1;
    }
    return 0;
}

static uint32_t apply_profile(uint32_t index, uint32_t timing, uint32_t tap)
{
    if (index >= sizeof(profiles) / sizeof(profiles[0]) ||
        tap > 31 || timing >= (1u << 18) || (timing & 3u) || !(timing >> 14))
        return 1;
    if (SWD_ID != SIGNATURE || !(SWD_STATUS & IDLE))
        return 2;

    uint32_t io_pll = MMIO(0xf8000108u);
    uint32_t bypass = (io_pll & 8u) ? MMIO(0xf800025cu) & 16u : io_pll & 16u;
    if (((io_pll >> 12) & 127u) != 48 || bypass || (io_pll & 3u) ||
        !(MMIO(0xf800010cu) & 4u))
        return 3;

    SWD_HOLD = 1;
    barrier();
    if (!wait_status(CLOCK_HELD | READY, CLOCK_HELD))
        return 4;

    /* Change only the PL reference divider. The initializer sets IO PLL x48. */
    uint32_t mask = 0x03f03f30u;
    uint32_t setting = (1u << 20) | (profiles[index].divisor << 8);
    if ((FCLK1_CTRL & mask) != setting) {
        MMIO(0xf8000008u) = 0xdf0du;
        FCLK1_CTRL = (FCLK1_CTRL & ~mask) | setting;
        MMIO(0xf8000004u) = 0x767bu;
        barrier();
    }
    MAILBOX[CLOCK_CTRL] = FCLK1_CTRL;
    if ((MAILBOX[CLOCK_CTRL] & mask) != setting)
        return 5;

    for (unsigned settle = 0; settle < 128; ++settle)
        (void)SWD_STATUS;
    SWD_TIMING = timing | profiles[index].rate;
    SWD_HOLD = 0;
    barrier();
    if (!wait_status(READY, READY)) {
        SWD_HOLD = 1;
        return 6;
    }
    SWD_TAP = tap;
    barrier();
    MAILBOX[SWCLK_HZ] = profiles[index].swclk_hz;
    return 0;
}

#ifdef SWD200_BOARD_BENCH
void bench_init(void);
void bench_poll(void);
#endif
void swd200_main(void)
{
    const uint32_t default_timing = (2u << 14) | (12u << 8) | (12u << 2);
    for (unsigned word = MAGIC; word <= SWCLK_HZ; ++word)
        MAILBOX[word] = 0;
    MAILBOX[TIMING] = default_timing;
    MAILBOX[ERROR] = apply_profile(0, default_timing, 0);
    barrier();
    MAILBOX[MAGIC] = SIGNATURE;
#ifdef SWD200_BOARD_BENCH
    bench_init();
#endif
    for (;;) {
#ifdef SWD200_BOARD_BENCH
        bench_poll();
#endif
        uint32_t request = MAILBOX[REQUEST];
        if (request == MAILBOX[RESPONSE])
            continue;
        barrier();
        MAILBOX[ERROR] = apply_profile(MAILBOX[PROFILE], MAILBOX[TIMING], MAILBOX[TAP]);
        barrier();
        MAILBOX[RESPONSE] = request;
    }
}
