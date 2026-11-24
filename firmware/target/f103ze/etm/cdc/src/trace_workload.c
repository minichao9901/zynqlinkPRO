#include "trace_workload.h"

volatile uint32_t g_trace_workload_digest;

__attribute__((noinline)) uint32_t trace_even(uint32_t value)
{
    return (value << 3) ^ (value >> 2) ^ 0x13579BDFu;
}

__attribute__((noinline)) uint32_t trace_odd(uint32_t value)
{
    return (value << 1) + (value >> 3) + 0x2468ACE1u;
}

__attribute__((noinline)) uint32_t trace_mix(uint32_t value, uint32_t count)
{
    for (uint32_t i = 0; i < count; ++i) {
        value = (value ^ (value >> 7)) * 33u + i;
    }
    return value;
}

/* Each complete round calls exactly eight alternating even/odd leaves.
 * The mix loop runs 1..8 times, providing known varying branch outcomes. */
__attribute__((noinline)) void trace_workload_round(uint32_t seed)
{
    uint32_t value = seed;
    for (uint32_t i = 0; i < 8u; ++i) {
        if ((i + seed) & 1u) {
            value = trace_odd(value);
        } else {
            value = trace_even(value);
        }
        value = trace_mix(value, i + 1u);
    }
    g_trace_workload_digest = value;
}
