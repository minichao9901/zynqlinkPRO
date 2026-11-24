#include "fixture.h"

const char g_build_id[] = FIXTURE_BUILD_ID;
SHARED volatile uint32_t g_boot_id, g_boot_data_verified, g_bss_probe;
SHARED volatile uint32_t g_watch_word, g_watch_read, g_watch_request;
SHARED volatile uint16_t g_watch_half;
SHARED volatile uint8_t g_watch_byte;
volatile uint32_t g_data_probe = 0x51a7da7au;

void debug_observables_init(void)
{
    g_boot_data_verified = (g_data_probe == 0x51a7da7au && g_bss_probe == 0);
    g_bss_probe = 0x5a5a5a5au;
    g_boot_id = FIXTURE_BUILD_MARKER;
    rtt_init();
    publish();
    g_fixture_ready = 0x44424731u;
}

void debug_observables_poll(void)
{
    if (g_watch_request) {
        uint32_t request = g_watch_request;
        uint32_t previous = g_watch_byte + g_watch_half + g_watch_word;
        g_watch_byte = request;
        g_watch_half = request;
        g_watch_word = request;
        g_watch_read = previous;
        g_watch_request = 0;
    }
#ifdef TARGET_H743
    /* Exercise FP thread context before PendSV preempts the debugger workload. */
    static volatile float thread_fp = 0.5f;
    float next = thread_fp + 0.125f;
    thread_fp = next < 1024.0f ? next : 0.5f;
#endif
    rtt_terminal_poll();
}
