"""Controlled RAM-only F103 fault, architectural exception return, full restore."""
import argparse,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from f103_ram_fixture import Fixture
from dap_pipeline_bench import open_dap,setup
from test_probe_board import Memory
from benchmark_rtt_forward import core_read,core_write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--pair',type=Path,required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:print('RAM-only fault fixture plan; no hardware access');return
    a.out.mkdir(parents=True,exist_ok=False)
    obj=a.out/'fault.o';elf=a.out/'fault.elf';binary=a.out/'fault.bin'
    subprocess.run(['arm-none-eabi-as','-mcpu=cortex-m3','-mthumb',str(ROOT/'tools/fixtures/f103_fault_return.S'),'-o',str(obj)],check=True)
    subprocess.run(['arm-none-eabi-ld','-Ttext=0x20002100','-e','fault_entry',str(obj),'-o',str(elf)],check=True)
    subprocess.run(['arm-none-eabi-objcopy','-O','binary',str(elf),str(binary)],check=True)
    symbols={line.split()[-1]:int(line.split()[0],16) for line in subprocess.check_output(['arm-none-eabi-nm','--defined-only',str(elf)],text=True).splitlines() if len(line.split())==3}
    f=Fixture(a.out/'fixture');f.__enter__();report={};safe_to_restore=True
    if f.regs[16]&511:
        f.__exit__(None,None,None)
        raise ValueError('fixture requires initial thread mode; original state restored')
    vtor=f.mem.word(0xe000ed08);cfsr=f.mem.word(0xe000ed28);hfsr=f.mem.word(0xe000ed2c)
    shcsr=f.mem.word(0xe000ed24)
    try:
        assert f.regs[16]&511==0,'fixture requires initial thread mode'
        vectors=bytearray(f.mem.read(vtor,64))
        for index in (3,6):vectors[index*4:index*4+4]=(symbols['fault_handler']|1).to_bytes(4,'little')
        f.mem.write(0x20002000,vectors);f.mem.write(0x20002100,binary.read_bytes());f.mem.write(0x20002300,bytes(8))
        f.mem.write_word(0xe000ed08,0x20002000)
        core_write(f.mem,17,0x20003000);core_write(f.mem,20,1);core_write(f.mem,16,0x01000000)
        core_write(f.mem,15,symbols['fault_entry']|1)
        f.release_dap();safe_to_restore=False
        command=[sys.executable,'-X','utf8',str(ROOT/'toolbox.py'),'trace','capture',
                 '--elf',str(ROOT/'prebuilt/golden/f103ze-cdc48.elf'),
                 '--bit',str(a.pair/'probe.bit'),'--zynq-elf',str(a.pair/'application.elf'),
                 '--out',str(a.out/'capture'),'--flight','--trigger','fault','--arm-timeout','5',
                 '--ring-bytes','1048576','--seconds','0.02','--swd-khz','10000','--no-decode']
        result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=60)
        (a.out/'cli.txt').write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
        report['cliReturncode']=result.returncode
        report['capture']=json.loads(result.stdout)
        assert result.returncode==0 and report['capture']['ok']
        acceptance=json.loads((a.out/'capture/acceptance.json').read_text(encoding='utf-8'))
        report['trigger']=acceptance['ddr']['flightTrigger']
        assert report['trigger']['source']=='fault' and report['trigger']['observedValue']&511 in (3,6)
    finally:
        if f.dev is None:
            f.dev,f.tx,f.rx=open_dap();f.mem=Memory(f.tx,f.rx);setup(f.tx,f.rx,1000)
        f.mem.write_word(0xe000edf0,0xa05f0003)
        active=f.mem.word(0xe000ed04)&511
        report['activeBeforeReturn']=active
        if active in (3,6):
            f.mem.write_word(0x20002304,1);f.resume()
            until=time.monotonic()+2
            while time.monotonic()<until:
                if not f.mem.word(0xe000ed04)&511:break
                time.sleep(.001)
            f.mem.write_word(0xe000edf0,0xa05f0003)
        safe_to_restore=not (core_read(f.mem,16)&511)
        report['exceptionReturned']=safe_to_restore
        if safe_to_restore:
            f.mem.write_word(0xe000ed08,vtor)
            f.mem.write_word(0xe000ed28,f.mem.word(0xe000ed28)&~cfsr)
            f.mem.write_word(0xe000ed2c,f.mem.word(0xe000ed2c)&~hfsr)
            report['faultRegistersRestored']=all(f.mem.word(addr)==value for addr,value in [(0xe000ed08,vtor),(0xe000ed28,cfsr),(0xe000ed2c,hfsr),(0xe000ed24,shcsr)])
            f.__exit__(None,None,None);report['restored']=f.report
        else:
            report['recoveryRequired']='Target left halted with RAM fixture intact; no reset or Flash write attempted'
            f.release_dap()
        (a.out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if not safe_to_restore:raise RuntimeError(report['recoveryRequired'])
    assert report['faultRegistersRestored']
    report['passed']=True;(a.out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
