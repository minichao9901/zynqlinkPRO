#include "fixture.h"

#define REG(address) (*(volatile uint32_t *)(address))
void enable_swo_pin(void);
SHARED volatile uint32_t g_itm_request, g_itm_sent, g_itm_busy, g_itm_port;

int main(void)
{
    if (!target_clock_init()) for (;;) {}
    enable_swo_pin();
    publish();
    g_fixture_ready = 0x49544d31u;
    uint32_t value = 0;
    for (;;) {
        uint32_t request = g_itm_request;
        uint32_t port = g_itm_port;
        if (value >= request || port >= 32 || !(REG(0xe0000e80u) & 1u) ||
            !(REG(0xe0000e00u) & (1u << port))) continue;
        if (!REG(0xe0000000u + 4u * port)) {
            ++g_itm_busy;
            continue;
        }
        REG(0xe0000000u + 4u * port) = value * 0x9e3779b9u ^ 0xa55aa55au;
        g_itm_sent = ++value;
    }
}
