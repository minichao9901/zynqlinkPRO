#include "cdc_console.h"

#include <string.h>

static uint8_t tx_queue[CDC_CONSOLE_TX_SIZE];
static size_t tx_head, tx_tail, tx_used;
static char line[CDC_CONSOLE_LINE_SIZE];
static size_t line_length;
static bool echo_enabled, binary_line, overlong_line;

void cdc_console_reset(void)
{
    tx_head = tx_tail = tx_used = 0;
    line_length = 0;
    echo_enabled = true;
    binary_line = overlong_line = false;
}

bool cdc_console_write(const uint8_t *data, size_t length)
{
    if (length > sizeof(tx_queue) - tx_used) {
        return false;
    }
    for (size_t i = 0; i < length; ++i) {
        tx_queue[tx_head] = data[i];
        tx_head = (tx_head + 1u) % sizeof(tx_queue);
    }
    tx_used += length;
    return true;
}

static void puts_queue(const char *text)
{
    /* feed() reserves enough space before accepting a command terminator. */
    (void)cdc_console_write((const uint8_t *)text, strlen(text));
}

static void handle_line(void)
{
    if (binary_line) {
        return; /* Binary loopback must not generate extra command responses. */
    }
    if (overlong_line) {
        if (!echo_enabled) {
            puts_queue("ERR LINE TOO LONG\r\n");
        }
        return;
    }
    if (line_length && line[line_length - 1u] == '\r') {
        --line_length;
    }
    line[line_length] = '\0';
    if (strcmp(line, "PING") == 0) {
        puts_queue("PONG\r\n");
    } else if (strcmp(line, "INFO") == 0) {
        char response[CDC_CONSOLE_RESPONSE_SIZE];
        size_t n = cdc_console_info(response, sizeof(response));
        if (n >= sizeof(response)) {
            n = sizeof(response) - 1u;
        }
        (void)cdc_console_write((const uint8_t *)response, n);
    } else if (strcmp(line, "MARK") == 0) {
        cdc_console_mark();
        puts_queue("OK MARK\r\n");
    } else if (strcmp(line, "ECHO on") == 0) {
        echo_enabled = true;
        puts_queue("OK ECHO on\r\n");
    } else if (strcmp(line, "ECHO off") == 0) {
        echo_enabled = false;
        puts_queue("OK ECHO off\r\n");
    } else if (strncmp(line, "ECHO ", 5) == 0) {
        puts_queue(line + 5);
        puts_queue("\r\n");
    } else if (line_length && !echo_enabled) {
        puts_queue("ERR UNKNOWN\r\n");
    }
}

size_t cdc_console_feed(const uint8_t *data, size_t length)
{
    size_t i;
    for (i = 0; i < length; ++i) {
        /* Backpressure: leave this byte untouched until the host drains TX.
         * Reserve raw echo + the largest reply, including INFO and CRLF. */
        if (sizeof(tx_queue) - tx_used < CDC_CONSOLE_RESPONSE_SIZE + 1u) {
            break;
        }
        uint8_t ch = data[i];
        if (echo_enabled) {
            (void)cdc_console_write(&ch, 1u);
        }
        if (ch == '\n') {
            handle_line();
            line_length = 0;
            binary_line = overlong_line = false;
        } else {
            if ((ch < 0x20u && ch != '\r') || ch > 0x7eu) {
                binary_line = true;
            }
            if (line_length < sizeof(line) - 1u) {
                line[line_length++] = (char)ch;
            } else {
                overlong_line = true;
            }
        }
    }
    return i;
}

size_t cdc_console_peek(uint8_t *data, size_t capacity)
{
    size_t n = tx_used < capacity ? tx_used : capacity;
    size_t pos = tx_tail;
    for (size_t i = 0; i < n; ++i) {
        data[i] = tx_queue[pos];
        pos = (pos + 1u) % sizeof(tx_queue);
    }
    return n;
}

void cdc_console_consume(size_t length)
{
    if (length > tx_used) {
        length = tx_used;
    }
    tx_tail = (tx_tail + length) % sizeof(tx_queue);
    tx_used -= length;
}
