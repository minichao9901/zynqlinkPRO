#include "fixture.h"
#include <stddef.h>
#include <string.h>

#ifndef FIXTURE_RING_BYTES
#define FIXTURE_RING_BYTES 8192
#endif
#define DOWN_SIZE 256u
#define BATCH_WORDS 128u

typedef struct {
    const char *name;
    uint8_t *buffer;
    uint32_t size;
    volatile uint32_t write, read;
    uint32_t flags;
} rtt_channel_t;

typedef struct {
    char id[16];
    uint32_t up_count, down_count;
    rtt_channel_t up, down;
} rtt_control_t;

_Static_assert(sizeof(rtt_channel_t) == 24 && offsetof(rtt_control_t, up) == 24 &&
               offsetof(rtt_control_t, down) == 48, "SEGGER RTT wire layout");

SHARED rtt_control_t _SEGGER_RTT;
SHARED static uint8_t up_bytes[FIXTURE_RING_BYTES], down_bytes[DOWN_SIZE];
SHARED volatile uint32_t g_rtt_published, g_rtt_consumed;
SHARED volatile uint32_t g_rtt_use_pattern, g_rtt_pattern;
static uint32_t sequence;
static char line[96];
static unsigned line_length;
extern const char g_build_id[];

void rtt_init(void)
{
    _SEGGER_RTT.up_count = 1;
    _SEGGER_RTT.down_count = 1;
    _SEGGER_RTT.up = (rtt_channel_t){"Terminal", up_bytes, sizeof up_bytes, 0, 0, 0};
    _SEGGER_RTT.down = (rtt_channel_t){"Terminal", down_bytes, sizeof down_bytes, 0, 0, 0};
    publish();
    memcpy(_SEGGER_RTT.id, "SEGGER RTT", sizeof "SEGGER RTT");
    publish();
}

static uint32_t free_bytes(const rtt_channel_t *ch)
{
    return (ch->read + ch->size - ch->write - 1u) & (ch->size - 1u);
}

static uint32_t stage(const uint8_t *data, uint32_t n, uint32_t offset)
{
    for (uint32_t i = 0; i < n; ++i) {
        up_bytes[offset] = data[i];
        offset = (offset + 1u) & (FIXTURE_RING_BYTES - 1u);
    }
    return offset;
}

static void commit(uint32_t next, uint32_t n)
{
    publish();
    _SEGGER_RTT.up.write = next;
    g_rtt_published += n;
}

void rtt_produce(void)
{
    if (free_bytes(&_SEGGER_RTT.up) < BATCH_WORDS * sizeof(uint32_t))
        return;
    uint32_t next = _SEGGER_RTT.up.write;
    bool fixed = g_rtt_use_pattern != 0;
    uint32_t pattern = g_rtt_pattern;
    for (unsigned i = 0; i < BATCH_WORDS; ++i) {
        uint32_t value = fixed ? pattern : sequence++;
        /* GCC emits a single word copy for the aligned streaming case. */
        if ((next & 3u) == 0) {
            __builtin_memcpy(up_bytes + next, &value, sizeof value);
            next = (next + sizeof value) & (FIXTURE_RING_BYTES - 1u);
            continue;
        }
        next = stage((const uint8_t *)&value, sizeof value, next);
    }
    commit(next, BATCH_WORDS * sizeof(uint32_t));
}

static void reply(const char *message, unsigned length)
{
    uint32_t next = stage((const uint8_t *)message, length, _SEGGER_RTT.up.write);
    next = stage((const uint8_t *)"\r\n", 2, next);
    commit(next, length + 2u);
}

SHARED volatile uint32_t g_rtt_binary_echo;

void rtt_terminal_poll(void)
{
    rtt_channel_t *down = &_SEGGER_RTT.down;
    if (down->read == down->write || free_bytes(&_SEGGER_RTT.up) < sizeof(line) + 2u)
        return;

    publish();
    uint8_t c = down_bytes[down->read];
    down->read = (down->read + 1u) & (DOWN_SIZE - 1u);
    ++g_rtt_consumed;
    if (g_rtt_binary_echo) {
        commit(stage(&c, 1, _SEGGER_RTT.up.write), 1);
        return;
    }
    if (c == '\r' || c == '\n') {
        if (!line_length) return;
        line[line_length] = '\0';
        if (!strcmp(line, "help")) {
            const char help[] = "help version echo <text>";
            reply(help, sizeof help - 1);
        } else if (!strcmp(line, "version")) {
            reply(g_build_id, strlen(g_build_id));
        } else if (!strncmp(line, "echo ", 5)) {
            reply(line + 5, line_length - 5);
        } else {
            reply("unknown command", 15);
        }
        line_length = 0;
    } else if (c == 8u || c == 127u) {
        if (line_length) --line_length;
    } else if (line_length + 1u < sizeof line) {
        line[line_length++] = (char)c;
    }
}
