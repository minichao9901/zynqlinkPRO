"""F103ZE SRAM/clock comparison with the historical J7 USB pair and S200."""
from contextlib import contextmanager
import argparse
import json
import struct
import time
import usb.util

from pathlib import Path
from swd200_board import Board, Ownership, PAIR, RTL, candidate, record, sha
from dap_pipeline_bench import open_dap, setup, xfer
from test_probe_board import Memory
from h743_peak import measure_pipeline
from test_swd_lowfreq_board import recover
import run_f103_clock_fixture as clocks

BASE = 0x20008000
REGS = dict(CR=clocks.CR, CFGR=clocks.CFGR, APB1ENR=clocks.APB1ENR, FLASH_ACR=clocks.FLASH)


def window_metrics(lines):
    """Decode successful, wholly verified windows. Preserve failures in the raw log."""
    rows = []
    for line in lines:
        if not line.startswith('WINDOW '):
            continue
        fields = [int(token) for token in line.split()[1:]]
        index, tap, ack, data, idle, mixed, rounds = fields[:7]
        hz, fclk, pll, timing = fields[7:11]
        box = fields[11:]
        if len(box) != 27 or box[5] or box[6] != rounds or box[7] != mixed * rounds:
            continue
        def us_per_block(field):
            ticks = box[field] | (box[field + 1] << 32)
            return ticks / (333333333 / 1e6) / rounds
        row = dict(profile=index, swclk_hz=hz, fclk_control=hex(fclk), io_pll=hex(pll),
                   timing=hex(timing), tap=tap, ack=ack, data=data, idle=idle, mixed=mixed,
                   rounds=rounds, read_waits=box[11], write_waits=box[12])
        for name, pos in [('read_scan', 13), ('write_scan', 15), ('read_local', 19), ('write_local', 21)]:
            us = us_per_block(pos)
            row[name + '_us'] = us
            if us:
                row[name + '_MB_s'] = 1024 / us
        row['compare_us'] = us_per_block(23)
        row['guard_us'] = us_per_block(25)
        rows.append(row)
    return rows


@contextmanager
def usb_link():
    deadline = time.monotonic()+25
    while True:
        device = None
        try:
            device, out, inp = open_dap('12345678')
            recover(device,inp)
            ident = setup(out, inp, 1000)
            break
        except (RuntimeError, usb.core.USBError):
            if device is not None:
                usb.util.dispose_resources(device)
            if time.monotonic() >= deadline:
                raise
            time.sleep(.25)
    try:
        mem = Memory(out, inp)
        assert ident[:7].hex() == '0501017714a01b' and mem.word(0xe0042000)==0x10036414
        yield mem
    finally:
        try:
            xfer(out,inp,[3])
        finally:
            usb.util.dispose_resources(device)


def clock_state(mem):
    return {k:mem.word(a) for k,a in REGS.items()}


def checked_ram(mem, original, guards, repair):
    assert [mem.word(BASE-4),mem.word(BASE+4096)]==guards
    before = mem.read(BASE,4096)
    if before!=original and repair:
        mem.write(BASE,original)
    assert mem.read(BASE,4096)==original
    assert [mem.word(BASE-4),mem.word(BASE+4096)]==guards


def bench_target(board, folder, original, guards, rates, diagnostics=False, guard=None, idle=2, points=None):
    import re
    pattern = (folder/'expected.bin').resolve()
    pattern.write_bytes(original[:1024])
    words=' '.join(map(str,struct.unpack('<1024I',original)))
    fixture=f'set saved {{{words}}}\nset guards {{{guards[0]} {guards[1]}}}\n'+(RTL/'f103ze.tcl').read_text()
    if guard is not None:
        fixture=f'set ::board_guard {guard}\n'+fixture
    board.tcl(f'physwr -force -bin -file {{{pattern.as_posix()}}} 0x24000 256')
    script=fixture+'\nf103_check 0\nset winners {}\n'
    script+='foreach rate {'+' '.join(map(str,rates))+'} {\n'+'''
        set candidates {}
        set responses {}
        foreach tap {8 0 16 24 31} {
            foreach slot {20 19 21 18 22 17 23 16 24 15 25 26 27 28} {
                swd_config $rate $tap $slot $slot 2
                set r [swd_batch {16 0 2 0 2 0 2 0}]
                dict incr responses [format %04x [expr {[lindex $r 0]&65535}]]
                if {([lindex $r 0]&65535)==4 && [lindex $r 2]==0x1ba01477 &&
                    [lindex $r 3]==0x1ba01477 && [lindex $r 4]==0x1ba01477} {
                    lappend candidates [list $tap $slot]
                }
            }
        }
        puts "ID_SUMMARY $rate $responses"
        if {![llength $candidates] && $rate==3} {
            foreach tap {0 8 16 24 31} {
                foreach slot {15 16 17 18 19 20 21 22 23 24 25} {
                    f103_low
                    swd_config $rate $tap $slot $slot 2
                    set r [swd_batch {2 0 2 0 2 0}]
                    if {([lindex $r 0]&65535)==3 && [lrange $r 1 end] eq [lrepeat 3 [expr {0x1ba01477}]]} {
                        lappend candidates [list $tap $slot]
                    }
                }
            }
            puts "SLOW_ENTRY $rate $candidates"
        }
        puts "CANDIDATES $rate $candidates"
        set ok 0
        foreach delta $phase_offsets {
        foreach idle {2 5 9 15} {
          foreach pair $candidates {
            lassign $pair tap slot
            set data [expr {$slot+$delta}]
            if {![f103_window $rate $tap $slot $data $idle 0 4]} continue
            if {![f103_window $rate $tap $slot $data $idle 1 4]} {f103_check 1;continue}
            f103_check 0
            if {[f103_window $rate $tap $slot $data $idle 1 256]} {
                f103_check 0
                lappend winners [list $rate $tap $slot $data $idle]
                puts "QUAL $rate $tap $slot $data $idle"
                set ok 1; break
            }
            f103_check 1
          }
          if {$ok} break
        }
        if {$ok} break
        }
    }
    set best 0
    foreach winner [lreverse $winners] {
        lassign $winner rate tap slot data idle
        # 'rates' is ordered by ascending physical clock.
        if {$best && $rate!=4 && $rate!=1 && $rate!=0} continue
        set rounds [expr {$best ? 1024 : 16384}]
        set ok 1
        for {set n 0} {$n<3} {incr n} {
            if {![f103_window $rate $tap $slot $data $idle 1 $rounds]} {f103_check 1; set ok 0;break}
            f103_check 0
        }
        if {$ok && !$best} {puts "STABLE $rate $tap $slot $data $idle";set best 1}
    }
    f103_check 1
    puts "FINAL [f103_word 0x40021004] [f103_word 0xe000edf0]"
    '''
    if diagnostics:
        script = fixture + '\nf103_check 0\nforeach rate {'+' '.join(map(str,rates))+'} {\n'+'''
          foreach tap {0 4 8 12 16 20 24 28 31} {
            foreach ack {15 16 17 18 19 20 21 22 23 24 25} {
              foreach delta {-2 -1 0 1 2} {
                set data [expr {$ack+$delta}]
                swd_config $rate $tap $ack $data 2
                set id [swd_batch {16 0 2 0 2 0 2 0}]
                if {([lindex $id 0]&65535)!=4 || [lrange $id 2 end] ne [lrepeat 3 [expr {0x1ba01477}]]} continue
                f103_low
                swd_require {5 0x20008000}
                swd_config $rate $tap $ack $data 2
                set commands [lrepeat 256 15 0];lappend commands 14 0
                set r [swd_batch $commands]
                set readok [expr {([lindex $r 0]&65535)==257 && [lrange $r 2 end] eq [lrange $saved 0 255]}]
                f103_low
                swd_require {5 0x20008004}
                swd_config $rate $tap $ack $data 2
                set w [swd_batch {5 0x20008000}]
                swd_config 0 0 20 20 8
                set stat [swd_batch {6 0}]
                set check [swd_batch {7 0 14 0}]
                set tarok [expr {([lindex $check 0]&65535)==2 && [lindex $check 2]==0x20008000}]
                puts "DIAG $rate $tap $ack $data $readok [lindex $r 0] [lindex $w 0] $tarok $stat $check"
                if {$readok && $tarok && [f103_window $rate $tap $ack $data 2 0 8]} {
                    set ok [f103_window $rate $tap $ack $data 2 1 8]
                    f103_check 1
                    if {$ok} {
                        set accepted 1
                        for {set n 0} {$n<3} {incr n} {
                            if {![f103_window $rate $tap $ack $data 2 1 16384]} {set accepted 0; f103_check 1; break}
                            f103_check 0
                        }
                        if {$accepted} {puts "EXTRA_STABLE $rate $tap $ack $data";set found 1;break}
                    }
                }
              }
              if {[info exists found]} break
            }
            if {[info exists found]} break
          }
          unset -nocomplain found
        }
        f103_check 1
        puts "FINAL [f103_word 0x40021004] [f103_word 0xe000edf0]"
        '''
    if points:
        script=fixture+'\nf103_check 0\n'
        for rate,tap,ack,data,spacing in points:
            params=f'{rate} {tap} {ack} {data} {spacing}'
            script+=f'''
            if {{[f103_window {params} 0 8] && [f103_window {params} 1 4]}} {{
                set ok 1
                for {{set n 0}} {{$n<3}} {{incr n}} {{
                    if {{![f103_window {params} 1 16384]}} {{set ok 0; break}}
                    f103_check 0
                }}
                if {{$ok}} {{puts "STABLE {params}"}}
            }}
            f103_check 1
            '''
        script+='puts "FINAL [f103_word 0x40021004] [f103_word 0xe000edf0]"'
    offsets = '0 -1 1 -2 2' if guard is not None else '0'
    script='set phase_offsets {'+offsets+'}\n'+script
    idles=' '.join(map(str,dict.fromkeys((idle,2,5,9,15))))
    script=script.replace('foreach idle {2 5 9 15}',f'foreach idle {{{idles}}}')
    output=board.tcl(script)
    record(folder/'timing.json', window_metrics(output.splitlines()))
    (folder/'windows.txt').write_text('\n'.join(x.rstrip() for x in output.splitlines() if re.match(r'^(QUAL|STABLE|FINAL|WINDOW|CANDIDATES|RECOVERED|DIAG|EXTRA_STABLE|ID_SUMMARY|SLOW_ENTRY) ',x))+'\n')
    print('\n'.join(x for x in output.splitlines() if x.startswith(('QUAL','STABLE','FINAL'))),flush=True)


def run(args):
    folder=args.out.resolve()
    folder.mkdir(parents=True,exist_ok=False)
    orig=args.original.read_bytes()
    assert len(orig)==4096
    guards=args.guards
    hist=tuple(args.historical/n for n in ('probe.bit','application.elf','ps7_init.tcl'))
    manifest=json.loads((args.historical/'manifest.json').read_text())
    assert all(sha(p)==manifest['files'][p.name]['sha256'] for p in hist)
    bit,_,init=candidate(args.pair)
    saved=None
    touched=False
    initial=None
    target={}
    try:
        with usb_link() as mem:
            checked_ram(mem,orig,guards,False)
            initial=mem.word(clocks.DHCSR)
            saved=clock_state(mem)
            assert saved['CFGR']==0x51040a
            target.update(initial_dhcsr=hex(initial),before=saved)
            record(folder/'target.json',target)
            if args.hclk!=48:
                touched=True
                mem.write_word(clocks.DHCSR,0xa05f0003)
                clocks.wait_bits(mem,clocks.DHCSR,1<<17,1<<17)
                clocks.set_hse8_clock(mem,saved,args.hclk//8,5,4)
                target['dwt']=clocks.dwt_check(mem,folder/'clock.json',args.hclk*1000000)
            target['active']=clock_state(mem)
            record(folder/'target.json',target)
            print('ACTIVE',args.hclk,target.get('dwt',{}).get('measured_Hz'),flush=True)
            try:
                setup(mem.out,mem.inp,66667,speed_hz=66666666)
                clock=xfer(mem.out,mem.inp,[0x80,255])
                hist_perf=measure_pipeline(mem,BASE,words=512,depth=32,loops=256,repeats=3,soak_seconds=3)
                hist_perf['probe_clock_reply']=clock.hex()
                record(folder/'historical.json',hist_perf)
            finally:
                setup(mem.out,mem.inp,1000)
                checked_ram(mem,orig,guards,True)
        try:
            b=Board(folder/'candidate',args.cable)
            b.load((bit,args.elf,init),experimental=True)
            bench_target(b,folder,orig,guards,args.rates,args.diagnostics,args.guard,args.idle,args.point)
        finally:
            b=Board(folder/'historical-restored',args.cable)
            b.load(hist,experimental=False)
    finally:
        if saved is not None:
            with usb_link() as mem:
                try:
                    checked_ram(mem,orig,guards,True)
                    target['ram_restored']=True
                finally:
                    if touched:
                        clocks.restore(mem,saved)
                        assert clock_state(mem)==saved
                        if not initial & (1<<17):
                            mem.write_word(clocks.DHCSR,0xa05f0000 | (initial&0x2d))
                target.update(after=clock_state(mem),final_dhcsr=hex(mem.word(clocks.DHCSR)))
                assert target['after']==saved and (int(target['final_dhcsr'],16)^initial)&(1<<17)==0
                record(folder/'target.json',target)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hclk',type=int,choices=(48,96,112,128),required=True)
    p.add_argument('--original',type=Path,required=True)
    p.add_argument('--historical',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--pair',type=Path,default=PAIR)
    p.add_argument('--guard',type=int,choices=range(8))
    p.add_argument('--idle',type=int,choices=range(16),default=2)
    p.add_argument('--guards',nargs=2,type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cable',required=True)
    p.add_argument('--rates',nargs='+',type=int,required=True)
    p.add_argument('--point',nargs=5,type=int,action='append',metavar=('PROFILE','TAP','ACK','DATA','IDLE'))
    p.add_argument('--execute',action='store_true')
    p.add_argument('--diagnostics',action='store_true',help='Split ACK/data phases and isolate a low-speed TAR setup from a high-speed TAR write')
    a=p.parse_args()
    if a.execute:
        lock=Ownership()
        try: run(a)
        finally: lock.close()
    else:
        print(f'F103ZE HCLK {a.hclk} MHz, SWD profiles {a.rates}, 4 KiB guarded backup.')
