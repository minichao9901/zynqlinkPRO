"""Control the F103ZE HAL storage example with explicit private backups.

The firmware's default loop is read-only. backup reads the affected NOR sector
and whole EEPROM twice. arm alone authorizes one test+restore transaction and
leaves the core halted for a subsequent trace-entry capture. verify rereads the
actual peripherals and compares them with the original host backup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import usb.util
from elftools.elf.elffile import ELFFile
from dap_pipeline_bench import open_dap,setup
from test_probe_board import Memory

FIELDS='magic version ready command ack state error jedec flash_bytes sector_address backup_valid arm flash_backup_fnv eeprom_backup_fnv flash_restored eeprom_restored read_rounds write_rounds verified_rounds spi_calls i2c_calls ticks last_hal_error last_command test_flash_fnv test_eeprom_fnv flash_dirty eeprom_dirty'.split()

def fnv(data):
    result=2166136261
    for v in data:result=((result^v)*16777619)&0xffffffff
    return result

class Storage:
    def __init__(self,elf):
        self.elf=Path(elf).resolve()
        with self.elf.open('rb') as stream:
            image=ELFFile(stream);symbols=image.get_section_by_name('.symtab')
            self.symbols={n:int(symbols.get_symbol_by_name(n)[0]['st_value']) for n in ['g_storage','storage_flash_backup','storage_eeprom_backup']}
            self.segments=[(int(v['p_paddr']),v.data()) for v in image.iter_segments() if v['p_type']=='PT_LOAD' and v['p_filesz'] and 0x08000000<=v['p_paddr']<0x08080000]
        self.dev,self.tx,self.rx=open_dap()
        try:
            setup(self.tx,self.rx,10000);self.mem=Memory(self.tx,self.rx)
            assert self.mem.word(0xe000ed00)==0x411fc231
            assert all(self.mem.read(addr,len(data))==data for addr,data in self.segments),'Running Flash differs from supplied ELF'
        except BaseException:
            usb.util.dispose_resources(self.dev);raise

    def close(self):usb.util.dispose_resources(self.dev)
    def state(self):
        words=struct.unpack('<28I',self.mem.read(self.symbols['g_storage'],112));state=dict(zip(FIELDS,words))
        assert state['magic']==0x53544f52 and state['version']==1 and state['ready']==1,state
        return state
    def field(self,name,value):self.mem.write_word(self.symbols['g_storage']+4*FIELDS.index(name),value)
    def halt(self):self.mem.write_word(0xe000edf0,0xa05f0003)
    def resume(self):self.mem.write_word(0xe000edf0,0xa05f0001)
    def command(self,command):
        before=self.state();assert not before['state'] and not before['command'],before
        self.field('command',command);self.resume();deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            state=self.state()
            if state['ack']==before['ack']+1:
                assert not state['error'],state
                return state
            time.sleep(.01)
        raise TimeoutError('Storage command incomplete: '+str(self.state()))
    def ram_backup(self):
        flash=self.mem.read(self.symbols['storage_flash_backup'],4096)
        eeprom=self.mem.read(self.symbols['storage_eeprom_backup'],256)
        state=self.state();assert state['backup_valid']
        assert fnv(flash)==state['flash_backup_fnv'] and fnv(eeprom)==state['eeprom_backup_fnv']
        return flash,eeprom

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['inspect','backup','arm','verify','restore'],required=True)
    p.add_argument('--elf',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--backup',type=Path);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print(json.dumps(dict(stage=a.stage,hardwareAccess=False)));return
    if a.stage in ('arm','verify','restore') and not a.backup:p.error('This stage requires an original --backup directory')
    a.out.mkdir(parents=True,exist_ok=False);report=dict(stage=a.stage,passed=False,targetFlashWrites=False,probeQspiWrites=False)
    target=Storage(a.elf)
    try:
        report['before']=target.state();report['elfSha256']=hashlib.sha256(a.elf.read_bytes()).hexdigest()
        if a.stage=='backup':
            report['after']=target.command(2);flash,eeprom=target.ram_backup()
            assert (flash,eeprom)==target.ram_backup()
            for name,data in [('nor-original.bin',flash),('eeprom-original.bin',eeprom)]:
                (a.out/name).write_bytes(data);report[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        elif a.stage in ('arm','verify','restore'):
            meta=json.loads((a.backup/'result.json').read_text(encoding='utf8'));assert meta['passed']
            flash=(a.backup/'nor-original.bin').read_bytes();eeprom=(a.backup/'eeprom-original.bin').read_bytes()
            assert hashlib.sha256(flash).hexdigest()==meta['nor-original.bin']['sha256']
            assert hashlib.sha256(eeprom).hexdigest()==meta['eeprom-original.bin']['sha256']
            assert report['before']['jedec']==meta['after']['jedec'] and report['before']['sector_address']==meta['after']['sector_address']
            if a.stage=='arm':
                target.halt();assert target.ram_backup()==(flash,eeprom)
                assert not report['before']['flash_dirty'] and not report['before']['eeprom_dirty']
                target.field('arm',0x53545257);target.field('command',3)
                report['after']=target.state();report['leftHaltedForTraceEntry']=True
            else:
                report['completedBeforeVerification']=not report['before']['state'] and not report['before']['command']
                if a.stage=='restore':
                    target.mem.write(target.symbols['storage_flash_backup'],flash);target.mem.write(target.symbols['storage_eeprom_backup'],eeprom)
                    target.field('flash_backup_fnv',fnv(flash));target.field('eeprom_backup_fnv',fnv(eeprom));target.field('backup_valid',1)
                    # Reset loses the RAM dirty flags. Explicit recovery must
                    # restore both backed-up regions even after a fresh boot.
                    target.field('flash_dirty',1);target.field('eeprom_dirty',1)
                    report['restore']=target.command(4)
                else:
                    assert report['completedBeforeVerification'] and not report['before']['error'],report['before']
                    assert report['before']['write_rounds']>0 and report['before']['write_rounds']==report['before']['verified_rounds']
                    assert report['before']['flash_restored'] and report['before']['eeprom_restored']
                    assert not report['before']['flash_dirty'] and not report['before']['eeprom_dirty']
                report['after']=target.command(2)
                assert target.ram_backup()==(flash,eeprom),'Independent peripheral reread differs from original host backup'
                report['peripheralsRestoredByteExact']=True
                report['norBytesVerified']=4096;report['eepromBytesVerified']=256
        else:report['after']=target.state()
        report['DHCSR']=hex(target.mem.word(0xe000edf0));report['RCC_CFGR']=hex(target.mem.word(0x40021004))
        report['passed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:
        (a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');target.close()
    print(json.dumps(report))

if __name__=='__main__':main()
