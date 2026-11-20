#include "dap_request.h"
#include <assert.h>
#include <stdio.h>

uint32_t dap_info_response_size(uint8_t id) {(void)id;return 2U;}
int dap_vendor_bounds(uint8_t command,dap_request_plan *plan) {
    (void)command;(void)plan;return 0;
}

int main(void) {
    dap_request_plan plan;
    const uint8_t read_all[]={0x1c,0xff,0xff};
    assert(DAP_ValidateCommand(read_all,3,4096,&plan));
    assert(plan.request_bytes==3 && plan.response_bytes==4096);
    assert(!DAP_ValidateCommand(read_all,2,4096,&plan));
    assert(!DAP_ValidateCommand(read_all,3,4095,&plan));
    const uint8_t empty[]={0x1c,0,0};
    assert(DAP_ValidateCommand(empty,3,4,&plan) && plan.response_bytes==4);
    const uint8_t compound[]={0x7f,2,0x1a,1,0x1c,0xff,0xff};
    assert(!DAP_ValidateCommand(compound,sizeof compound,4096,&plan));
    uint8_t extended[]={0x1e,0};
    for(unsigned mask=0;mask<8;mask++) {
        extended[1]=(uint8_t)mask;
        unsigned bytes=1+(mask&1U)+((mask&2U)?4:0)+((mask&4U)?8:0);
        assert(DAP_ValidateCommand(extended,2,bytes,&plan));
        assert(plan.request_bytes==2 && plan.response_bytes==bytes);
        assert(!DAP_ValidateCommand(extended,2,bytes-1,&plan));
    }
    extended[1]=8;
    assert(!DAP_ValidateCommand(extended,2,4096,&plan));
    const uint8_t baudrate[]={0x19,0,0,0,0};
    assert(DAP_ValidateCommand(baudrate,5,5,&plan));
    assert(!DAP_ValidateCommand(baudrate,4,5,&plan));
    puts("PASS SelectIO SWO maximum/empty/truncated reads, extended fields and compound bounds");
    return 0;
}
