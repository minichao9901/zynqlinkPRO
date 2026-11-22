#ifndef SELECTIO_AUX_H
#define SELECTIO_AUX_H
#include <stdint.h>
#include "xusbps.h"
#define SELECTIO_SERIAL_DDR_BYTES (2U*1024U*1024U)
#define SELECTIO_SERIAL_BUFFER_BYTES (SELECTIO_SERIAL_DDR_BYTES+65536U)
void selectio_aux_poll(void);
void selectio_cdc_status(uint32_t values[8]);
int selectio_aux_conflict(unsigned port);
int selectio_cdc_bind(unsigned enable);
int selectio_cdc_receiving(void);
int selectio_cdc_space(void);
void selectio_cdc_receive(const uint8_t *data,unsigned length);
int selectio_cdc_complete(void *data);
void selectio_cdc_poll(XUsbPs *usb);
void selectio_cdc_reset(void);
void selectio_cdc_line(unsigned baud);
void selectio_cdc_resume_rx(XUsbPs *usb);
int selectio_aux_frame(unsigned channel,unsigned op,const uint8_t *in,unsigned size,
                       uint8_t *out,unsigned capacity,unsigned *length,unsigned *consume);
void selectio_aux_consume(unsigned bytes);
int selectio_aux_reset(void);
int selectio_aux_native_owner(void);
int selectio_aux_release_native(void);
void selectio_swo_reset(void);
uint32_t selectio_swo_command(uint8_t command,const uint8_t *request,uint8_t *response);
int selectio_aux_exclusive(void);
int selectio_aux_busy_for_clock(void);
#endif
