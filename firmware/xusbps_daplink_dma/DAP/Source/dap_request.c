#include "dap_request.h"

/* Sizes include the command byte. Bounds are checked before every payload
 * access, including commands that the wire executor may stop halfway through. */
int dap_validate_one(const uint8_t *p, uint32_t length, uint32_t capacity,
                     dap_request_plan *plan) {
    uint32_t in=1,out=1,count,i,n,flags;
    if(!p || !plan || !length || !capacity)return 0;
    switch(p[0]) {
    case 0x00: /* Info strings are pure CPU data, at most 255 bytes. */
        if(length<2)return 0;
        in=2;out=dap_info_response_size(p[1]);break;
    case 0x01: in=3;out=2;break;
    case 0x02: in=2;out=2;break;
    case 0x03: in=1;out=2;break;
    case 0x04: in=6;out=2;break;
    case 0x05: /* index, count, (request [, data/match])* */
        if(length<3)return 0;
        in=3;out=3;count=p[2];
        for(i=0;i<count;i++) {
            if(in>=length)return 0;
            flags=p[in++];
            if(flags&0x40U)return 0; /* reserved */
            if(!(flags&2U) || (flags&0x10U)) {
                if(length-in<4)return 0;
                in+=4;
            }
            if((flags&2U) && !(flags&0x10U))out+=4;
            if(flags&0x80U)out+=4; /* conservative when timestamp disabled */
        }
        break;
    case 0x06:
        if(length<5)return 0;
        count=p[2]|((uint32_t)p[3]<<8);flags=p[4];
        if(flags&0xf0U)return 0;
        in=5;out=4;
        if(flags&2U)out+=4*count;else in+=4*count;
        break;
    case 0x08: in=6;out=2;break;
    case 0x09: in=3;out=2;break;
    case 0x0a: out=3;break;
    case 0x10: in=7;out=2;break;
    case 0x11: in=5;out=2;break;
    case 0x12:
        if(length<2)return 0;
        count=p[1]?p[1]:256;in=2+(count+7)/8;out=2;break;
    case 0x13: in=2;out=2;break;
    case 0x14: /* JTAG sequences: TDI always present, TDO optional. */
    case 0x1d: /* SWD sequences: DIN has no request payload. */
        if(length<2)return 0;
        in=2;out=2;count=p[1];
        for(i=0;i<count;i++) {
            if(in>=length)return 0;
            flags=p[in++];n=flags&63U;n=((n?n:64)+7)/8;
            if(p[0]==0x14 || !(flags&0x80U)) {
                if(length-in<n)return 0;
                in+=n;
            }
            if(flags&0x80U)out+=n;
        }
        break;
    case 0x15:
        if(length<2)return 0;
        in=2+p[1];out=2;break;
    case 0x16: in=2;out=6;break;
    default:
        /* Nested Execute/Queue, disabled SWO/UART and unknown commands are
         * rejected. Extensions must supply bounds before being enabled. */
        if(p[0]<0x80 || p[0]>0x9f || !dap_vendor_bounds(p[0],plan))return 0;
        in=plan->request_bytes;out=plan->response_bytes;
        if(p[0]==0x8c && (length<28 || p[2]!=0x45 || p[3]!=0x44))return 0;
        break;
    }
    if(in>length || out>capacity)return 0;
    plan->request_bytes=in;plan->response_bytes=out;return 1;
}

int DAP_ValidateCommand(const uint8_t *p,uint32_t length,uint32_t capacity,
                        dap_request_plan *plan) {
    uint32_t in=2,out=2,i;dap_request_plan child;
    if(!p || !plan || !length || !capacity || length>65535 || capacity>65535)return 0;
    if(p[0]!=0x7e && p[0]!=0x7f)return dap_validate_one(p,length,capacity,plan);
    if(length<2 || capacity<2)return 0;
    for(i=0;i<p[1];i++) {
        if(!dap_validate_one(p+in,length-in,capacity-out,&child))return 0;
        in+=child.request_bytes;out+=child.response_bytes;
    }
    plan->request_bytes=in;plan->response_bytes=out;return 1;
}
