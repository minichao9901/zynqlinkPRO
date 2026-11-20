#ifndef SELECTIO_COMBO_H
#define SELECTIO_COMBO_H
#include <stdint.h>
int selectio_combo_active(void);
int selectio_combo_stop(void);
void selectio_combo_reset(void);
void selectio_combo_poll(void);
void selectio_combo_commit(unsigned source,unsigned n);
int selectio_combo_frame(unsigned op,const uint8_t *request,unsigned size,
                         uint8_t *reply,unsigned capacity,unsigned *length,unsigned *consume,unsigned *source);
#endif
