"""Execute real TransferConfigure and JTAG route packing against a CSR model."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


def body(source, declaration):
    start = source.index(declaration)
    brace = source.index('{', start)
    depth = 1
    for i in range(brace + 1, len(source)):
        depth += (source[i] == '{') - (source[i] == '}')
        if depth == 0:
            return source[start:i + 1]
    raise AssertionError('Function body not found')


class IdleConfigurationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gcc'), 'native compiler unavailable')
    def test_real_idle_capability_and_legacy_cfg_are_preserved(self):
        route = body((ROOT/'firmware/xusbps_daplink_dma/DAP/Source/JTAG_RTL.c').read_text(), 'uint32_t DAP_JTAG_RouteWord(')
        configure = body((ROOT/'firmware/xusbps_daplink_dma/DAP/Source/DAP.c').read_text(), 'static uint32_t DAP_TransferConfigure(')
        vendor = (ROOT/'firmware/xusbps_daplink_dma/DAP/Source/DAP_vendor.c').read_text()
        query_case = vendor[vendor.index('case ID_DAP_Vendor13:'):vendor.index('case ID_DAP_Vendor14:')]
        query = '\n#define ID_DAP_Vendor13 13\n#define DAP_ERROR 255\nstatic uint32_t query_idle(uint8_t *request,uint8_t *response){uint32_t num=0;switch(13){'+query_case+'}return num;}\n'
        prefix = r'''
#include <stdint.h>
#include <assert.h>
#define DAP_PORT_JTAG 2
#define DAP_OK 0
#define SWD_CFG 8U
#define SWD_FEATURES 76U
#define JTAG_ROUTE 128U
#define JTAG_FEATURE_EXTENDED_IDLE 32U
static struct {uint32_t debug_port;struct {uint8_t idle_cycles;uint16_t retry_count,match_retry;} transfer;} DAP_Data;
static uint32_t cfg,features,idcode_ir,route_value,writes;
static uint32_t swd_read32(uint32_t at){assert(at==SWD_CFG||at==SWD_FEATURES||at==JTAG_ROUTE);return at==SWD_CFG?cfg:at==JTAG_ROUTE?route_value:features;}
static void swd_write32(uint32_t at,uint32_t v){assert(at==SWD_CFG||at==JTAG_ROUTE);if(at==SWD_CFG)cfg=v;else{route_value=v;writes++;}}
static uint32_t JTAG_IDCodeIR(void){return idcode_ir;}
'''
        checks = r'''
static void check(uint32_t port,uint32_t ir,uint32_t feature,uint8_t requested,uint8_t expected,int extended){
 uint8_t req[5]={requested,0x34,0x12,0x78,0x56},response=99;
 DAP_Data.debug_port=port;idcode_ir=ir;features=feature;cfg=0xabcd0101;writes=0;route_value=0;
 assert(DAP_TransferConfigure(req,&response)==((5U<<16)|1U)&&response==DAP_OK);
 assert(DAP_Data.transfer.idle_cycles==expected);
 assert(DAP_Data.transfer.retry_count==0x1234&&DAP_Data.transfer.match_retry==0x5678);
 assert(cfg==((0xabcd0101U&~0xf0U)|((expected>15?15:expected)<<4)));
 assert(writes==(unsigned)extended);
 if(extended)assert(((route_value>>16)&255)==(expected>15?expected:0));
 uint8_t q=255,r[3]={99,99,99};uint32_t count=query_idle(&q,r);
 assert(count==((2U<<16)|4U)&&r[0]==DAP_OK);
 assert(r[2]==(extended?64:15));
 assert(r[1]==((extended&&expected<8)?8:expected));
}
int main(void){
 check(2,1,32,24,24,1);check(2,1,32,64,64,1);check(2,1,32,255,64,1);
 check(2,1,32,8,8,1);check(2,1,32,0,1,1);
 check(2,1,0,24,15,0);check(2,14,32,24,15,0);check(1,1,32,24,15,0);
 return 0;
}
'''
        out = ROOT/'build/riscv_idle_config_test'
        out.mkdir(exist_ok=True)
        cfile, exe = out/'test.c', out/('test.exe' if os.name == 'nt' else 'test')
        cfile.write_text(prefix + route + configure + query + checks)
        cc = ['gcc']
        if os.name == 'nt' and shutil.which('clang'):
            mingw = Path(shutil.which('gcc')).parent.parent
            libs = list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
            cc = ['clang', '--target=x86_64-w64-windows-gnu', '-isystem', str(mingw/'include'), '-L'+str(mingw/'lib'), '-L'+str(libs[-1])]
        subprocess.run([*cc, '-std=c11', '-Wall', str(cfile), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
