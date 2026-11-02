"""Execute production DAP_SWJ_Clock against a bounded MMIO/PS clock model."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RiscvClockPolicyTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('gcc'), 'native C compiler unavailable')
    def test_real_clock_command_preserves_tck_and_arm_policy(self):
        source = (ROOT/'firmware/xusbps_daplink_dma/DAP/Source/DAP.c').read_text()
        start = source.index('static uint32_t DAP_SWJ_Clock(')
        end = source.index('{', start)
        depth = 1
        for at in range(end + 1, len(source)):
            depth += (source[at] == '{') - (source[at] == '}')
            if not depth:
                production = source[start:at + 1]
                break
        else:
            self.fail('Clock command body not found')
        shim = r'''
#include <stdint.h>
#include <assert.h>
#define DAP_SWD 1
#define DAP_JTAG 1
#define DAP_FIXED_FCLK0_TEST 0
#define DAP_MAX_SWCLK_HZ 60000000U
#define DAP_PORT_SWD 1
#define DAP_PORT_JTAG 2
#define DAP_OK 0
#define DAP_ERROR 255
#define SWD_CFG 8U
#define SWD_FEATURES 76U
#define SWD_FEATURE_SHORT_CLOCK (1U<<4)
static struct {uint32_t debug_port;} DAP_Data;
static uint32_t cfg,ir,fclk,calls;
static uint32_t swd_read32(uint32_t at){assert(at==SWD_CFG || at==SWD_FEATURES);return at==SWD_CFG?cfg:SWD_FEATURE_SHORT_CLOCK;}
static void swd_write32(uint32_t at,uint32_t value){assert(at==SWD_CFG);cfg=value;}
static uint32_t JTAG_IDCodeIR(void){return ir;}
static unsigned owned;
static unsigned etm_ddr_owned(void){return owned;}
static int ps_fixed133_select(void){fclk=133333332U;calls++;return (int)fclk;}
static int ps_set_fclk0_hz(uint32_t requested){assert(requested<=120000000U);fclk=requested-1;calls++;return (int)fclk;}
static void Set_Clock_Delay(uint32_t hz){(void)hz;}
static void DAP_JTAG_ClockChanged(void){}
'''
        checks = r'''
static void check(uint32_t hz,uint32_t port,uint32_t opcode,uint32_t expected_fclk,uint32_t half){
 uint8_t req[4]={hz,hz>>8,hz>>16,hz>>24},reply=99;
 DAP_Data.debug_port=port;ir=opcode;cfg=0;calls=0;
 assert(DAP_SWJ_Clock(req,&reply)==((4U<<16)|1U));
 if(!expected_fclk){assert(reply==DAP_ERROR && calls==0 && cfg==0);return;}
 assert(reply==DAP_OK && calls==1 && fclk+1==expected_fclk);
 uint32_t observed_half=1+((cfg>>13)&15)+(((cfg>>28)&15)<<4);
 assert(observed_half==half && fclk/(2U*observed_half)<=hz);
 if(port==DAP_PORT_JTAG){assert(observed_half<=16 && !(cfg&(1U<<19)));}
}
int main(void){
 check(1000000,2,1,32000000,16);
 check(5000000,2,1,120000000,12);
 check(10000000,2,1,120000000,6);
 check(14000000,2,1,112000000,4);
 check(15000000,2,1,30000000,1);
 check(25000000,2,1,50000000,1);
 check(10000000,2,14,20000000,1);
 check(10000000,1,1,120000000,6);
 check(0,2,1,0,0);check(249999,2,1,0,0);check(60000001,2,1,0,0);
 return 0;
}
'''
        out = ROOT/'build/riscv_clock_policy_test'
        out.mkdir(parents=True, exist_ok=True)
        cfile, exe = out/'test.c', out/('test.exe' if os.name == 'nt' else 'test')
        cfile.write_text(shim + production + checks)
        compiler = ['gcc']
        if os.name == 'nt' and shutil.which('clang'):
            mingw = Path(shutil.which('gcc')).parent.parent
            libs = list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
            compiler = ['clang', '--target=x86_64-w64-windows-gnu', '-isystem', str(mingw/'include'),
                        '-L'+str(mingw/'lib'), '-L'+str(libs[-1])]
        subprocess.run([*compiler, '-std=c11', '-Wall', '-Wextra', str(cfile), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)
        # Execute the same production function with the explicitly verified
        # 133MHz build cap. Ordinary profiles must keep their prior policy.
        extended = (shim.replace('#define DAP_MAX_SWCLK_HZ 60000000U', '#define DAP_MAX_SWCLK_HZ 66666666U')
            .replace('requested<=120000000U', 'requested<=133333332U'))
        extended_checks = (checks.replace('check(5000000,2,1,120000000,12)', 'check(5000000,2,1,130000000,13)')
            .replace('check(60000001,2,1,0,0)', 'check(66666667,2,1,0,0);check(66666666,2,1,133333333,1);check(65000000,2,1,130000000,1)')
            .replace(' return 0;', ' owned=1;check(66666666,2,1,0,0);return 0;'))
        cfile.write_text(extended + production + extended_checks)
        subprocess.run([*compiler, '-std=c11', '-Wall', '-Wextra', str(cfile), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
