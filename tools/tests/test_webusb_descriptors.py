"""Compile and execute the production BOS/URL generator with a host C ABI."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class WebUsbDescriptors(unittest.TestCase):
    def test_production_bos_keeps_winusb_and_advertises_https_url(self):
        compiler=shutil.which('gcc')
        if not compiler:self.skipTest('Host C compiler unavailable')
        command=[compiler]
        if os.name=='nt' and shutil.which('clang'):
            mingw=Path(compiler).parent.parent
            libs=list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
            command=['clang','--target=x86_64-w64-windows-gnu','-isystem',str(mingw/'include'),
                     '-L'+str(mingw/'lib'),'-L'+str(libs[-1])]
        source=ROOT/'firmware/xusbps_daplink_dma'
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            (out/'xil_types.h').write_text('#include <stdint.h>\ntypedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;\n')
            (out/'test.c').write_text(r'''
#include <assert.h>
#include <string.h>
#include "xusbps_bos_desc.h"
int main(void) {
    u8 buffer[256];
    assert(XUsbPs_Ch9SetupBosDescReply(buffer,sizeof(buffer))==57);
    assert(buffer[0]==5 && buffer[1]==15 && buffer[2]==57 && buffer[3]==0 && buffer[4]==2);
    assert(buffer[5]==28 && buffer[31]==MS_OS_20_VENDOR_CODE);
    assert(buffer[33]==24 && buffer[34]==16 && buffer[35]==5);
    const u8 uuid[]={0x38,0xb6,0x08,0x34,0xa9,0x09,0xa0,0x47,0x8b,0xfd,0xa0,0x76,0x88,0x15,0xb6,0x65};
    assert(!memcmp(buffer+37,uuid,16));
    assert(buffer[53]==0 && buffer[54]==1 && buffer[55]==WEBUSB_VENDOR_CODE && buffer[56]==1);
    assert(XUsbPs_Ch9SetupBosDescReply(buffer,56)==0);
    assert(XUsbPs_Ch9SetupBosDescReply(0,256)==0);
    u32 n=XUsbPs_Ch9SetupWebUsbUrlReply(buffer,sizeof(buffer));
    assert(n==3+strlen(WEBUSB_LANDING_URL) && buffer[0]==n && buffer[1]==3 && buffer[2]==1);
    assert(!memcmp(buffer+3,WEBUSB_LANDING_URL,n-3));
    assert(XUsbPs_Ch9SetupWebUsbUrlReply(buffer,n-1)==0);
    assert(XUsbPs_Ch9SetupWebUsbUrlReply(0,256)==0);
    assert(XUsbPs_Ch9SetupMsOs20DescReply(buffer,sizeof(buffer))==178);
    assert(buffer[8]==178 && buffer[9]==0 && !memcmp(buffer+30,"WINUSB",6));
    return 0;
}
''')
            exe=out/'test.exe'
            built=subprocess.run([*command,'-Wall','-Wextra','-I'+str(out),'-I'+str(source),
                str(out/'test.c'),str(source/'xusbps_bos_desc.c'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)


if __name__=='__main__':unittest.main()
