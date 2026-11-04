#ifndef DAP_WAIT_H
#define DAP_WAIT_H
#include <stdint.h>
#ifndef DAP_VALIDATION_FAULTS
#define DAP_VALIDATION_FAULTS 0
#endif
enum {DAP_WAIT_TIMEOUT=1,DAP_WAIT_CANCEL=2,DAP_WAIT_EPOCH=3};
void dap_wait_begin(void);
void dap_wait_init(void);
void dap_context_publish(uint32_t flags,uint32_t failures,uint32_t first_stage,
                          uint32_t select,uint32_t csw,uint32_t tar);
unsigned dap_wait_command_error(void);
int dap_wait_status(uint32_t address,uint32_t mask,uint32_t expected,
                     uint32_t wire_bits,uint32_t *last);
int dap_validation_restore_fault(unsigned stage);
#endif
