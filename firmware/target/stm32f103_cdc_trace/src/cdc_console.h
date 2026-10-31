#ifndef CDC_CONSOLE_H
#define CDC_CONSOLE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

/* Main-loop-owned queue. Callers serialize USB reset/DTR callbacks with polling. */
#define CDC_CONSOLE_TX_SIZE 4096u
#define CDC_CONSOLE_LINE_SIZE 128u
#define CDC_CONSOLE_RESPONSE_SIZE 256u

void cdc_console_reset(void);
size_t cdc_console_feed(const uint8_t *data, size_t length);
bool cdc_console_write(const uint8_t *data, size_t length);
size_t cdc_console_peek(uint8_t *data, size_t capacity);
void cdc_console_consume(size_t length);

/* Board callbacks, invoked only by cdc_console_feed() in the main loop. */
size_t cdc_console_info(char *data, size_t capacity);
void cdc_console_mark(void);

#endif
