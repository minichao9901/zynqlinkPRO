#include "cdc_console.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned marks;

size_t cdc_console_info(char *data, size_t capacity)
{
    const char info[] = "chip=STM32H7B0 sysclk=280000000Hz\r\n";
    assert(capacity >= sizeof(info));
    memcpy(data, info, sizeof(info));
    return sizeof(info) - 1u;
}

void cdc_console_mark(void) { ++marks; }

static void feed_text(const char *text)
{
    assert(cdc_console_feed((const uint8_t *)text, strlen(text)) == strlen(text));
}

static void expect_text(const char *text)
{
    uint8_t actual[CDC_CONSOLE_TX_SIZE];
    size_t n = cdc_console_peek(actual, sizeof(actual));
    assert(n == strlen(text));
    assert(memcmp(actual, text, n) == 0);
    /* Peeking must leave bytes queued when a transport start fails. */
    uint8_t retry[CDC_CONSOLE_TX_SIZE];
    assert(cdc_console_peek(retry, sizeof(retry)) == n);
    assert(memcmp(actual, retry, n) == 0);
    cdc_console_consume(n);
}

static void command_mode(void)
{
    cdc_console_reset();
    feed_text("ECHO off\r\n");
    expect_text("ECHO off\r\nOK ECHO off\r\n");
}

static void test_default_echo_and_replies(void)
{
    cdc_console_reset();
    feed_text("PING\r\n");
    expect_text("PING\r\nPONG\r\n");
    feed_text("ECHO hello\n");
    expect_text("ECHO hello\nhello\r\n");
}

static void test_fragmented_and_coalesced_commands(void)
{
    command_mode();
    feed_text("PI");
    expect_text("");
    feed_text("NG\r");
    expect_text("");
    feed_text("\nINFO\nMARK\r\n");
    expect_text("PONG\r\nchip=STM32H7B0 sysclk=280000000Hz\r\nOK MARK\r\n");
    assert(marks == 1u);
}

static void test_explicit_echo_and_unknown(void)
{
    command_mode();
    feed_text("ECHO hello-cherryusb\r\nNOSUCHCMD\n\r\n");
    expect_text("hello-cherryusb\r\nERR UNKNOWN\r\n");
    feed_text("ECHO on\n");
    expect_text("OK ECHO on\r\n");
    feed_text("loopback-12345");
    expect_text("loopback-12345");
}

static void test_long_and_binary_lines(void)
{
    command_mode();
    uint8_t long_line[256];
    memset(long_line, 'A', sizeof(long_line));
    assert(cdc_console_feed(long_line, sizeof(long_line)) == sizeof(long_line));
    feed_text("\nPING\n");
    expect_text("ERR LINE TOO LONG\r\nPONG\r\n");
    const uint8_t binary[] = { 0, 'P', 'I', 'N', 'G', '\n' };
    assert(cdc_console_feed(binary, sizeof(binary)) == sizeof(binary));
    expect_text("");
    feed_text("PING\n");
    expect_text("PONG\r\n");
}

static void test_printable_loopback(void)
{
    cdc_console_reset();
    uint8_t payload[512], output[512];
    memset(payload, 'X', sizeof(payload));
    payload[sizeof(payload) - 1u] = '\n';
    assert(cdc_console_feed(payload, sizeof(payload)) == sizeof(payload));
    assert(cdc_console_peek(output, sizeof(output)) == sizeof(payload));
    assert(memcmp(output, payload, sizeof(payload)) == 0);
    cdc_console_consume(sizeof(payload));
    expect_text("");
}

static void test_backpressure_and_wraparound(void)
{
    cdc_console_reset();
    uint8_t payload[50000], output[137];
    for (size_t i = 0; i < sizeof(payload); ++i) {
        payload[i] = (uint8_t)i;
    }
    size_t accepted = cdc_console_feed(payload, sizeof(payload));
    assert(accepted > 0 && accepted < sizeof(payload));
    assert(cdc_console_feed(payload + accepted, sizeof(payload) - accepted) == 0);
    size_t drained = 0;
    while (drained < sizeof(payload)) {
        size_t n = cdc_console_peek(output, sizeof(output));
        assert(n > 0);
        assert(memcmp(output, payload + drained, n) == 0);
        cdc_console_consume(n);
        drained += n;
        accepted += cdc_console_feed(payload + accepted, sizeof(payload) - accepted);
    }
    assert(accepted == sizeof(payload));
    expect_text("");
}

static void test_reply_survives_full_queue(void)
{
    command_mode();
    uint8_t filler[CDC_CONSOLE_TX_SIZE];
    memset(filler, 0xa5, sizeof(filler));
    assert(cdc_console_write(filler, sizeof(filler)));
    assert(!cdc_console_write(filler, 1));
    assert(cdc_console_feed((const uint8_t *)"PING\n", 5) == 0);
    cdc_console_consume(sizeof(filler));
    feed_text("PING\n");
    expect_text("PONG\r\n");
}

static void test_reset_clears_session(void)
{
    command_mode();
    feed_text("PI");
    assert(cdc_console_write((const uint8_t *)"old", 3));
    cdc_console_reset();
    expect_text("");
    feed_text("PING\n");
    expect_text("PING\nPONG\r\n");
}

int main(void)
{
    test_default_echo_and_replies();
    test_fragmented_and_coalesced_commands();
    test_explicit_echo_and_unknown();
    test_long_and_binary_lines();
    test_printable_loopback();
    test_backpressure_and_wraparound();
    test_reply_survives_full_queue();
    test_reset_clears_session();
    puts("PASS: 8 CDC console regression scenarios");
    return 0;
}
