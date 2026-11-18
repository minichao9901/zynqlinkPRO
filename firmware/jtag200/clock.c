/* Bare-metal JTAG experiment: configure the isolated serializer clock on
 * demand through the low-OCM mailbox. The GP0 waveform RAM is host driven. */
#include <stdint.h>

#define REG32(address) (*(volatile uint32_t *)(address))
#define MAILBOX ((volatile uint32_t *)0x0002ff00u)
#define SIGNATURE 0x4a323030u /* J200 */
#define FPGA_ID     REG32(0x40000000u)
#define FPGA_STATUS REG32(0x40000004u)
#define FPGA_CTRL   REG32(0x40000008u)
#define FPGA_DELAY  REG32(0x4000000cu)
#define FCLK1_CTRL  REG32(0xf8000180u)

enum { READY = 1, DONE = 2, CALIBRATED = 4, RUN = 8, HOLD = 2 };
enum { MAGIC, REQUEST, PROFILE, TAPS, RESPONSE, ERROR, CLOCK_CTRL, TCK_HZ, HALF_SLOTS };

struct profile {
    uint32_t divisor;
    uint32_t half_slots;
    uint32_t tck_hz;
};

static const struct profile profiles[] = {
    {32, 4, 50000000},
    {32, 3, 66666667},
    {40, 2, 80000000},
    {32, 2, 100000000},
    {40, 1, 160000000},
    {32, 1, 200000000},
    /* Two complete TCKs per serializer word for the block engine. */
    {48, 2, 66666667},
    /* One-slot profiles for bracketing the board-level frequency limit. */
    {48, 1, 133333333},
    {43, 1, 148837209},
    {39, 1, 164102564},
    {38, 1, 168421053},
    {37, 1, 172972973},
    {36, 1, 177777778},
    {35, 1, 182857143},
    {34, 1, 188235294},
    {33, 1, 193939394}
};

static void barrier(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
}

static int wait_status(uint32_t mask, uint32_t wanted)
{
    for (unsigned attempt = 0; attempt < 100000; ++attempt) {
        if ((FPGA_STATUS & mask) == wanted)
            return 1;
    }
    return 0;
}

static uint32_t select_clock(uint32_t profile, uint32_t taps)
{
    if (profile >= sizeof(profiles) / sizeof(profiles[0]) || taps > 31)
        return 1;
    if (FPGA_ID != SIGNATURE || (FPGA_STATUS & (RUN | DONE)))
        return 2;

    /* The initializer supplies the existing 33.333 MHz PS reference and
     * IO PLL x48. Never retune a PLL or the FCLK0/FCLK2 divisors. */
    uint32_t io_pll = REG32(0xf8000108u);
    uint32_t bypass = (io_pll & 8u) ? REG32(0xf800025cu) & 16u : io_pll & 16u;
    if (((io_pll >> 12) & 127u) != 48 || bypass || (io_pll & 3u) ||
        !(REG32(0xf800010cu) & 4u))
        return 3;

    FPGA_CTRL = HOLD;
    barrier();
    if (!wait_status(READY, 0))
        return 4;
    uint32_t mask = 0x03f03f30u;
    uint32_t setting = (1u << 20) | (profiles[profile].divisor << 8);
    if ((FCLK1_CTRL & mask) != setting) {
        REG32(0xf8000008u) = 0xdf0du;
        FCLK1_CTRL = (FCLK1_CTRL & ~mask) | setting;
        REG32(0xf8000004u) = 0x767bu;
        barrier();
    }
    MAILBOX[CLOCK_CTRL] = FCLK1_CTRL;
    if ((MAILBOX[CLOCK_CTRL] & mask) != setting)
        return 5;

    /* Bound the reset pulse independently of the restarting clock. */
    for (unsigned settle = 0; settle < 128; ++settle)
        (void)FPGA_STATUS;
    FPGA_CTRL = 0;
    barrier();
    if (!wait_status(READY | CALIBRATED, READY | CALIBRATED)) {
        FPGA_CTRL = HOLD;
        return 6;
    }
    FPGA_DELAY = taps;
    barrier();
    MAILBOX[TCK_HZ] = profiles[profile].tck_hz;
    MAILBOX[HALF_SLOTS] = profiles[profile].half_slots;
    return 0;
}

#ifdef JTAG200_STRESS
void stress_init(void);
void stress_poll(void);
#endif

void jtag200_main(void)
{
    /* The RAM loader resets the A9 before entry. Keep MMIO and the physical
     * MEM-AP mailbox uncached for the full experiment. */
    for (unsigned word = MAGIC; word <= HALF_SLOTS; ++word)
        MAILBOX[word] = 0;
    MAILBOX[ERROR] = select_clock(0, 0);
    barrier();
    MAILBOX[MAGIC] = SIGNATURE;
#ifdef JTAG200_STRESS
    stress_init();
#endif
    for (;;) {
        uint32_t request = MAILBOX[REQUEST];
        if (request == MAILBOX[RESPONSE]) {
#ifdef JTAG200_STRESS
            stress_poll();
#endif
            continue;
        }
        barrier();
        MAILBOX[ERROR] = select_clock(MAILBOX[PROFILE], MAILBOX[TAPS]);
        barrier();
        MAILBOX[RESPONSE] = request;
    }
}
