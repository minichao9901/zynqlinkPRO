#ifndef SELECTIO_MODE_H
#define SELECTIO_MODE_H
#include <stdint.h>
/* These functions access GP1 only after checking the capability on legacy GP0. */
int selectio_live_available(void);
int selectio_live_active(void);
uint32_t selectio_live_config(void);
int selectio_live_set(uint32_t config);
int selectio_live_clock(void);
uint32_t selectio_live_hz(void);
int selectio_live_profile(unsigned port,unsigned tap,unsigned slot,unsigned idle);
#endif
