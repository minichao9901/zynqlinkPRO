#include "probe_host_platform.h"
#include "descriptor_under_test.c"
const uint32_t probe_hid_report_size=29;
int main(void) {
    uint8_t buf[256];uint32_t len,off=0,mask=0,endpoints=0;unsigned intf=0,expected=0,seen=0;
    memset(buf,0xaa,sizeof(buf));assert(XUsbPs_Ch9SetupCfgDescReply(buf,8)==0 && buf[0]==0xaa);
    len=XUsbPs_Ch9SetupCfgDescReply(buf,sizeof(buf));
    assert(len==144 && buf[2]==144 && buf[3]==0 && buf[4]==4);
    while(off<len) {
        unsigned n=buf[off],type=buf[off+1];assert(n>=2 && off+n<=len);
        if(type==4) {
            assert(seen==expected);intf=buf[off+2];expected=buf[off+4];seen=0;
            assert(intf<4 && !(mask&(1U<<intf)));mask|=1U<<intf;
            if(intf==0) assert(expected==4 && buf[off+5]==0xff);
            if(intf==3) assert(expected==2 && buf[off+5]==3);
        } else if(type==5) {
            unsigned ep=buf[off+2],mps=buf[off+4]|(buf[off+5]<<8);seen++;
            unsigned bit=(ep&15)+(ep&128 ? 16 : 0);assert(!(endpoints&(1U<<bit)));endpoints|=1U<<bit;
            if(intf==0) assert(mps==512 && (ep==2 || ep==0x81 || ep==0x82 || ep==0x87));
            if(intf==3) assert(mps==64 && buf[off+3]==3 && (ep==6 || ep==0x86));
        } else if(type==0x21) assert(n==9 && buf[off+7]==probe_hid_report_size);
        else if(type==11) assert(buf[off+2]==1 && buf[off+3]==2);
        else if(type==0x24 && buf[off+2]==6) assert(buf[off+3]==1 && buf[off+4]==2);
        off+=n;
    }
    assert(mask==15 && seen==expected);
    assert(XUsbPs_Ch9SetupDevDescReply(buf,256)==18 && buf[12]==1 && buf[13]==1);
    assert(XUsbPs_Ch9SetupStrDescReply(buf,256,4)>4);
    puts("PASS production USB descriptors: total length, interface/endpoint counts, unique addresses, CDC IAD/union, HID report length");
    return 0;
}
