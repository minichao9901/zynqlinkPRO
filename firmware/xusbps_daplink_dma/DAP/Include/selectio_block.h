#ifndef SELECTIO_BLOCK_H
#define SELECTIO_BLOCK_H
#include <stdint.h>
/* Vendor 14 request excluding its command byte:
 * port (low nibble, bit 7 = write), u16 word count, u32 address,
 * IDELAY tap, RX slot, idle clocks, reserved byte, then write payload.
 * Response: status, u32 hardware result, then verified-length read payload.
 */
uint32_t selectio_block(const uint8_t *request, uint8_t *response);
void selectio_mem_stats(uint64_t values[7]);
int selectio_mem_bulk(unsigned write,uint32_t address,unsigned words,const uint8_t *payload,uint8_t *reply,unsigned *completed,uint32_t *detail);
int selectio_mem_open(const uint8_t profile[4]);
int selectio_mem_close(void);
int selectio_mem_active(void);
#endif
