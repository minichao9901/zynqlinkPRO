"""Exercise the real BOOT writer against a NOR command/status model."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]


class ProgrammerTests(unittest.TestCase):
    def test_guards_sector_bounds_page_edges_busy_and_verify_failures(self):
        compiler=shutil.which('gcc')
        if not compiler:self.skipTest('Host C compiler unavailable')
        command=[compiler]
        if os.name=='nt' and shutil.which('clang'):
            mingw=Path(compiler).parent.parent;libs=list((mingw/'lib/gcc/x86_64-w64-mingw32').glob('*'))
            command=['clang','--target=x86_64-w64-windows-gnu','-isystem',str(mingw/'include'),'-L'+str(mingw/'lib'),'-L'+str(libs[-1])]
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            (out/'xqspips.h').write_text('typedef int XQspiPs; int XQspiPs_PolledTransfer(XQspiPs*,unsigned char*,unsigned char*,unsigned);\n')
            for name in ['xparameters.h','xil_cache.h']:(out/name).write_text('')
            (out/'sleep.h').write_text('void usleep(unsigned);\n')
            code=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
static unsigned model_mail[16],sr,writes,erases,pages,sleeps,stuck,corrupt,bank;
static unsigned char model_data[8192],flash[16384];
#define PROGRAM_MODEL 1
#define MAIL model_mail
#define DATA model_data
'''+ '#include "'+(ROOT/'firmware/boot/qspi_program.c').as_posix()+'"\n'+r'''
void usleep(unsigned n){assert(n==1000);sleeps++;}
int XQspiPs_PolledTransfer(XQspiPs *p,unsigned char *tx,unsigned char *rx,unsigned n){
 (void)p;memset(rx,0,264);
 if(tx[0]==5){assert(n==2);rx[1]=sr;return 0;}
 if(tx[0]==6){assert(n==1);sr|=2;writes++;return 0;}
 if(tx[0]==4){assert(n==1);sr&=~2U;return 0;}
 if(tx[0]==0xe9){assert(n==1);return 0;}
 if(tx[0]==0xc8){assert(n==2);rx[1]=bank;return 0;}
 unsigned a=tx[0]==0x13?((unsigned)tx[1]<<24)|((unsigned)tx[2]<<16)|((unsigned)tx[3]<<8)|tx[4]:((unsigned)tx[1]<<16)|((unsigned)tx[2]<<8)|tx[3];
 assert(a<sizeof(flash));
 if(tx[0]==0x20){assert(n==4 && (sr&2) && !(a&4095));memset(flash+a,255,4096);sr=stuck?1:0;erases++;return 0;}
 if(tx[0]==2){assert((sr&2) && n>4 && n<=260 && !(a&255));
  for(unsigned k=0;k<n-4;k++)flash[a+k]&=tx[4+k];sr=0;pages++;return 0;}
 assert(tx[0]==0x13 && n<=261);memcpy(rx+5,flash+a,n-5);
 if(corrupt && pages)rx[5]^=1;return 0;
}
static void reset(void){
 sr=writes=erases=pages=sleeps=stuck=corrupt=bank=0;
 memset(model_mail,0,sizeof(model_mail));memset(flash,0x5a,sizeof(flash));
 for(unsigned i=0;i<sizeof(model_data);i++)model_data[i]=i*13U+7U;
 memcpy(model_data+0x20,"\x66\x55\x99\xaa\x58\x4e\x4c\x58",8);
}
int main(void){
 reset();unsigned c=crc32(model_data,513);
 assert(program_boot(0,c,ARM_KEY,0xef4019)==1 && !writes);
 assert(program_boot(LIMIT+1,c,ARM_KEY,0xef4019)==1 && !writes);
 assert(program_boot(513,c,0,0xef4019)==1 && !writes);
 assert(program_boot(513,c,ARM_KEY,0x123456)==1 && !writes);
 model_data[0x20]^=1;assert(program_boot(513,c,ARM_KEY,0xef4019)==2 && !writes);
 model_data[0x20]^=1;assert(program_boot(513,c^1,ARM_KEY,0xef4019)==3 && !writes);
 sr=4;assert(program_boot(513,c,ARM_KEY,0xef4019)==4 && !writes);
 sr=0;bank=1;assert(program_boot(513,c,ARM_KEY,0xef4019)==15 && !writes);
 for(unsigned z=0;z<4;z++){
  reset();unsigned lengths[]={256,257,4096,4097};unsigned n=lengths[z];
  assert(program_boot(n,crc32(model_data,n),ARM_KEY,0xef4019)==0);
  assert(!memcmp(model_data,flash,n));unsigned end=(n+4095)&~4095U;
  for(unsigned k=n;k<end;k++)assert(flash[k]==255);
  for(unsigned k=end;k<sizeof(flash);k++)assert(flash[k]==0x5a);
  assert(erases==end/4096 && pages==(n+255)/256 && !sr && MAIL[7]==n);
 }
 reset();stuck=1;assert(program_boot(513,crc32(model_data,513),ARM_KEY,0xef4019)==6);
 assert(sleeps==5000 && pages==0 && erases==1);
 reset();corrupt=1;assert(program_boot(513,crc32(model_data,513),ARM_KEY,0xef4019)==11);
 assert(pages==1 && MAIL[7]==0);
 return 0;
}
'''
            (out/'model.c').write_text(code)
            built=subprocess.run([*command,'-std=c11','-Wall','-Wextra','-I'+str(out),str(out/'model.c'),'-o',str(out/'model.exe')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(out/'model.exe')],capture_output=True,text=True,timeout=10)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
