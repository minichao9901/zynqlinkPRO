#include "fixture.h"

typedef struct {
    uint32_t before[8];
    uint32_t words[4096];
    uint32_t after[8];
} scratch_t;

#ifdef FIXTURE_HPM_AHB
static volatile scratch_t *const scratch = (volatile scratch_t *)0xf0401000u;
SHARED volatile uint32_t g_perf_sram_address;
#else
SHARED volatile scratch_t g_perf_sram;
static volatile scratch_t *const scratch = &g_perf_sram;
#endif
SHARED volatile uint32_t g_mode, g_scope_updates, g_scope[8], g_scope_update_hz = 0;
SHARED volatile uint32_t g_perf_sram_bytes;
SHARED volatile struct {
    uint8_t counter;
    int8_t saw;
    uint16_t ramp;
    int16_t square;
    float level;
} g_scope_mixed;
const char g_build_id[] = FIXTURE_BUILD_ID;

int main(void)
{
    if (!target_clock_init()) for (;;) {}
#ifdef FIXTURE_HPM_AHB
    g_perf_sram_address = (uintptr_t)&scratch->words[0];
#endif
    g_perf_sram_bytes = sizeof scratch->words;
    for (unsigned i = 0; i != 8; ++i) {
        scratch->before[i] = 0x51a70000u | i;
        scratch->after[i] = 0xbadc0000u | i;
    }
    for (unsigned i = 0; i != 4096; ++i)
        scratch->words[i] = 0x9e3779b9u * (i + 1);
    rtt_init();
    g_scope_update_hz = 10000;
    uint32_t period = target_tick_hz() / g_scope_update_hz;
    uint32_t deadline = target_tick() + period;
    publish();
    g_fixture_ready = 0x46585046u;
    for (;;) {
        uint32_t mode = g_mode;
        if ((mode & 2u) && (int32_t)(target_tick() - deadline) >= 0) {
            uint32_t tick = g_scope_updates + 1u;
            g_scope[0] = tick;
            g_scope[1] = ~tick;
            g_scope[2] = tick % 100u;
            g_scope[3] = (tick % 10u < 5u) ? 1000u : (uint32_t)-1000;
            g_scope[4] = tick * 0x9e3779b9u;
            g_scope[5] = tick % 2000u < 100u;
            g_scope[6] = 0x80000000u | (tick & 0xffffu);
            g_scope[7] = tick;
            g_scope_mixed.counter = tick;
            g_scope_mixed.saw = (int8_t)(3u * tick);
            g_scope_mixed.ramp = tick % 1000u;
            g_scope_mixed.square = tick % 10u < 5u ? 1000 : -1000;
            union { uint32_t bits; float value; } level = {0x3f800000u | (tick & 0xffffu)};
            g_scope_mixed.level = level.value;
            g_scope_updates = tick;
            deadline += period;
        } else if (!(mode & 2u)) {
            deadline = target_tick() + period;
        }
        if (mode & 1u)
            rtt_produce();
        else
            rtt_terminal_poll();
    }
}
