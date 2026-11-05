"""Exercise production SWD sequence functions against a strict pin/MMIO model."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, signature):
    begin = source.index(signature)
    brace = source.index('{', begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[begin:end]


class SWDSequenceTests(unittest.TestCase):
    def test_real_pin_helpers_and_command_mixed_sequences(self):
        compiler = shutil.which('gcc')
        if not compiler:
            self.skipTest('Host C compiler unavailable')
        command = [compiler]
        if os.name == 'nt' and shutil.which('clang'):
            mingw = Path(compiler).parent.parent
            libs = list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
            command = ['clang','--target=x86_64-w64-windows-gnu','-isystem',str(mingw/'include'),
                       '-L'+str(mingw/'lib'),'-L'+str(libs[-1])]
        config = (ROOT/'firmware/xusbps_daplink_dma/DAP/Include/DAP_config.h').read_text(encoding='utf8')
        dap = (ROOT/'firmware/xusbps_daplink_dma/DAP/Source/DAP.c').read_text(encoding='utf8')
        swd = (ROOT/'firmware/xusbps_daplink_dma/DAP/Source/SW_DP.c').read_text(encoding='utf8')
        helpers = ['PIN_SWCLK_TCK_SET','PIN_SWCLK_TCK_CLR','PIN_SWDIO_IN','PIN_SWDIO_OUT',
                   'PIN_SWDIO_OUT_ENABLE','PIN_SWDIO_OUT_DISABLE']
        source = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define __STATIC_FORCEINLINE static inline
#define DAP_SWD 1
#define DAP_PORT_SWD 1
#define DAP_OK 0
#define DAP_ERROR 255
#define SWD_SEQUENCE_CLK 63
#define SWD_SEQUENCE_DIN 128
#define SWD_FEATURES 0x4001004cU
#define SWD_FEATURE_MANUAL_DIRECTION 64
#define JTAG_PINS 0x40010094U
static struct {unsigned debug_port;} DAP_Data;
static uint32_t pins,features;
static unsigned io_writes, read_count, write_count, edges, releases;
static uint8_t written[64];
static uint32_t swd_read32(uint32_t address) {
    if(address==SWD_FEATURES) return features;
    assert(address==JTAG_PINS);
    uint32_t value=pins;
    if(pins&0x200U) value=(value&~2U)|(((read_count*7U+3U)&1U)<<1);
    return value;
}
static void swd_write32(uint32_t address,uint32_t value) {
    assert(address==JTAG_PINS); /* Any old GPIO access fails this assertion. */
    io_writes++;
    if(!(pins&0x200U) && (value&0x200U)) releases++;
    if(!(pins&1U) && (value&1U)) {
        edges++;
        if(value&0x200U) read_count++;
        else written[write_count++]=(value>>1)&1U;
    }
    pins=value;
}
'''
        for helper in helpers:
            signature = next(line.strip() for line in config.splitlines()
                             if line.startswith('__STATIC_FORCEINLINE') and (helper+' ') in line)
            source += function(config, signature)
            source += '\n'
        source += r'''
#define SW_WRITE_BIT(bit) do { PIN_SWDIO_OUT(bit); PIN_SWCLK_TCK_CLR(); PIN_SWCLK_TCK_SET(); } while(0)
#define SW_READ_BIT(bit) do { PIN_SWCLK_TCK_CLR(); bit=PIN_SWDIO_IN(); PIN_SWCLK_TCK_SET(); } while(0)
'''
        source += function(swd, 'void SWD_Sequence (') + '\n'
        source += function(dap, 'static uint32_t DAP_SWD_Sequence(') + '\n'
        source += r'''
int main(void) {
    for(unsigned n=1;n<=64;n++) {
        uint8_t request[12]={2,0}, response[16];
        unsigned bytes=(n+7)/8;
        request[1]=n&63;
        for(unsigned j=0;j<bytes;j++) request[2+j]=0xa5U+17U*j;
        request[2+bytes]=128|(n&63);
        memset(response,0xa5,sizeof(response));
        DAP_Data.debug_port=1; features=64; pins=0; edges=read_count=write_count=releases=0;
        unsigned result=DAP_SWD_Sequence(request,response);
        assert(result==(((3+bytes)<<16)|(1+bytes)));
        assert(response[0]==0 && response[1+bytes]==0xa5 && edges==2*n);
        assert(read_count==n && write_count==n && releases==1 && !(pins&0x200U));
        for(unsigned j=0;j<n;j++) {
            assert(written[j]==((request[2+j/8]>>(j%8))&1));
            assert(((response[1+j/8]>>(j%8))&1)==((j*7U+3U)&1));
        }
        if(n%8) assert(!(response[bytes]>> (n%8)));
        for(unsigned port=0;port<=2;port++) {
            DAP_Data.debug_port=port; features=port==1?0:64;
            unsigned old=io_writes;
            memset(response,0xa5,sizeof(response));
            result=DAP_SWD_Sequence(request,response);
            assert(result==(((3+bytes)<<16)|(1+bytes)));
            assert(response[0]==255 && io_writes==old);
            for(unsigned j=1;j<=bytes;j++) assert(response[j]==0);
            assert(response[bytes+1]==0xa5);
        }
    }
    puts("PASS production 0x1D mixed input/output 1..64 bits, true SWDIO MMIO, old-bit and non-SWD rejection");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            code = folder/'sequence.c'
            exe = folder/'sequence.exe'
            code.write_text(source, encoding='utf8')
            subprocess.run([*command,'-std=c11','-O2','-Wall','-Wextra','-Werror',str(code),'-o',str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
