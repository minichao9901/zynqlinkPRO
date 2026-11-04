#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include "dap_request.h"
static unsigned effects,fail_next;
static unsigned wait_error;
unsigned dap_wait_command_error(void) {return wait_error;}
uint32_t dap_info_response_size(uint8_t id) {return id==1 ? 257U : 4U;}
int dap_vendor_bounds(uint8_t id,dap_request_plan *p) {
    if(id!=0x8c)return 0;
    p->request_bytes=28;p->response_bytes=178;return 1;
}
/* The checked executor's only wire-operation dependency. Failures deliberately
 * report a shorter consumed-input count to check composite offset ownership. */
static uint32_t DAP_ProcessCommand(const uint8_t *p,uint8_t *q) {
    dap_request_plan plan;assert(dap_validate_one(p,4096,4096,&plan));effects++;
    if(p[0]==0x11) {q[0]=p[0];q[1]=0;return (5U<<16)|2;}
    if(fail_next){wait_error=1;fail_next=0;}
    q[0]=p[0];return (1U<<16)|1U;
}
/* Generated test includes the unchanged public executor body from DAP.c. */
#include "dap_checked_executor_under_test.h"

static void rejected(const uint8_t *p,unsigned n,unsigned cap) {
    uint8_t out[4100];memset(out,0xa5,sizeof out);unsigned before=effects;
    assert(DAP_ExecuteCommand(p,n,out+2,cap)==(cap?1U:0U));
    assert(effects==before && out[0]==0xa5 && out[1]==0xa5);
    if(cap)assert(out[2]==0xff);
    for(unsigned i=3;i<sizeof out;i++)assert(out[i]==0xa5);
}
int main(void) {
    dap_request_plan plan;uint8_t req[4100]={6,0,0xff,3,2};
    assert(DAP_ValidateCommand(req,5,4096,&plan)&&plan.response_bytes==4096);
    req[2]=0;req[3]=4;rejected(req,5,4096); /* actual old 4100B-overflow input */
    req[2]=0xff;req[3]=0xff;rejected(req,5,4096);
    req[2]=0xff;req[3]=3;rejected(req,5,4095);
    for(unsigned n=0;n<5;n++)rejected(req,n,4096);
    req[4]=0;rejected(req,4096,4096); /* 1023 writes need 4097 input bytes */
    req[2]=0xfe;assert(DAP_ValidateCommand(req,4093,4,&plan));
    rejected(req,4092,4096);
    uint8_t clock[]={0x11,0x80,0x96,0x98,0};
    for(unsigned n=0;n<5;n++)rejected(clock,n,4096);
    uint8_t composite[]={0x7f,2,0x11,0x80,0x96,0x98,0,6,0,0,4,2};
    rejected(composite,sizeof composite,4096);assert(effects==0);
    uint8_t nested[]={0x7f,1,0x7f,0};rejected(nested,sizeof nested,4096);
    uint8_t queue_nested[]={0x7f,1,0x7e,0};rejected(queue_nested,sizeof queue_nested,4096);
    uint8_t too_many[]={0x7f,255,3};rejected(too_many,sizeof too_many,4096);
    uint8_t vendors[64]={0x8c,1,0x45,0x44};
    for(unsigned n=0;n<28;n++)rejected(vendors,n,4096);
    rejected(vendors,28,177);assert(DAP_ValidateCommand(vendors,28,178,&plan));
    vendors[2]=0;rejected(vendors,28,4096);
    uint8_t seq[]={0x1d,2,0x80,0x00}; /* DIN64 then missing DOUT64 */
    rejected(seq,sizeof seq,4096);
    uint8_t jtag[]={0x14,1,0x80,0,0,0,0,0,0,0,0};
    assert(DAP_ValidateCommand(jtag,sizeof jtag,10,&plan)&&plan.response_bytes==10);
    rejected(jtag,sizeof jtag-1,4096);rejected(jtag,sizeof jtag,9);
    uint8_t transfer[]={5,0,2,0x92,1,2,3,4,0x0f};
    assert(DAP_ValidateCommand(transfer,sizeof transfer,11,&plan));
    rejected(transfer,sizeof transfer-1,4096);rejected(transfer,sizeof transfer,10);
    uint8_t info[]={0,1};rejected(info,2,256);assert(DAP_ValidateCommand(info,2,257,&plan));
    uint8_t valid[]={0x7f,2,5,0,1,0x0f,0x11,0x80,0x96,0x98,0},out[64]={0};
    assert((DAP_ExecuteCommand(valid,sizeof valid,out,sizeof out)&65535)==5);
    assert(effects==2 && out[0]==0x7f && out[1]==2 && out[2]==5 && out[3]==0x11);
    fail_next=1;effects=0;
    assert((DAP_ExecuteCommand(valid,sizeof valid,out,sizeof out)&65535)==3);
    assert(effects==1 && out[1]==1);wait_error=0;
    uint32_t rng=0x11111215;
    for(unsigned i=0;i<50000;i++) {
        unsigned n=i%128;
        for(unsigned j=0;j<n;j++){rng=rng*1664525U+1013904223U;req[j]=(uint8_t)(rng>>24);}
        unsigned cap=(i*13)%4097;
        if(DAP_ValidateCommand(req,n,cap,&plan))assert(plan.request_bytes<=n && plan.response_bytes<=cap);
    }
    puts("PASS checked DAP: old 4100B overflow, truncated scalar/block/sequence/vendor, atomic compounds, nesting, capacities and 50000 bounded fuzz inputs");
}
