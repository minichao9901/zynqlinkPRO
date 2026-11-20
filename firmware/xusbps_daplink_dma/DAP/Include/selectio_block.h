#ifndef SELECTIO_BLOCK_H
#define SELECTIO_BLOCK_H
#include <stdint.h>
/* Vendor 14 request excluding its command byte:
 * port (low nibble, bit 7 = write), u16 word count, u32 address,
 * IDELAY tap, RX slot, idle clocks, reserved byte, then write payload.
 * Response: status, u32 hardware result, then verified-length read payload.
 */
uint32_t selectio_block(const uint8_t *request, uint8_t *response);
#endif
