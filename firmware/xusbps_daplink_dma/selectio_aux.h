#ifndef SELECTIO_AUX_H
#define SELECTIO_AUX_H
#include <stdint.h>
int selectio_aux_frame(unsigned channel,unsigned op,const uint8_t *in,unsigned size,
                       uint8_t *out,unsigned capacity,unsigned *length,unsigned *consume);
void selectio_aux_consume(unsigned bytes);
void selectio_aux_reset(void);
int selectio_aux_exclusive(void);
#endif
