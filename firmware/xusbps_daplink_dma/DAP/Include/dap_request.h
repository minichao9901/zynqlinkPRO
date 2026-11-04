#ifndef DAP_REQUEST_H
#define DAP_REQUEST_H
#include <stdint.h>
typedef struct { uint32_t request_bytes, response_bytes; } dap_request_plan;
/* Pure preflight: no MMIO, target commands or changes to protocol state. */
uint32_t dap_info_response_size(uint8_t id);
int dap_vendor_bounds(uint8_t command, dap_request_plan *plan);
int dap_validate_one(const uint8_t *request, uint32_t length, uint32_t capacity,
                     dap_request_plan *plan);
int DAP_ValidateCommand(const uint8_t *request, uint32_t length, uint32_t capacity,
                        dap_request_plan *plan);
#endif
