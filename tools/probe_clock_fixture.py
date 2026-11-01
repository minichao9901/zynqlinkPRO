"""Temporary, STA-bounded FCLK0 profile for offline board acceptance.

The serializer divider preserves the existing SWD rate by default. Explicit
capture setup may select a slower standard waveform and records that change.
No target RCC, PLL, Flash, firmware policy, or independent FCLK1 is changed.
"""
import hashlib
import json
import math
from pathlib import Path
try:from .zynq_clock import fclk_hz,pll_hz
except ImportError:from zynq_clock import fclk_hz,pll_hz


def plan(control, pll, cfg, requested, *, destination_source=0, destination_pll=None, allow_link_reduction=False):
    if pll & 0x13:
        raise ValueError('Requires running PLL source')
    destination_pll=pll if destination_pll is None else destination_pll
    if destination_pll & 0x13:raise ValueError('Requires running destination PLL')
    destination_hz=pll_hz(destination_pll)
    if not ((control >> 8) & 63) or not ((control >> 20) & 63) or requested<=0:
        raise ValueError('Invalid clock divisor or requested rate')
    old_hz = fclk_hz(control,pll)
    old_half = 1 + ((cfg >> 13) & 15) + (((cfg >> 28) & 15) << 4)
    if cfg & (1 << 19) and not allow_link_reduction:
        raise ValueError('Short high-pulse profile cannot preserve its waveform')
    choices = [(destination_hz // a // b, a, b) for a in range(1,64) for b in range(1,64)
               if destination_hz // a // b <= requested]
    hz, a, b = max(choices)
    half = round(hz * old_half / old_hz)
    # Integer register readouts can differ by one Hz due to floor operations.
    exact=not(cfg&(1<<19)) and 1<=half<=256 and abs(hz*old_half-old_hz*half)<=max(half,old_half)
    if not exact and not allow_link_reduction:
        raise ValueError('Requested FCLK cannot preserve the external link frequency')
    new_cfg = (cfg & ~0xf001e000) | (((half-1) & 15) << 13) | (((half-1) >> 4) << 28)
    if not exact:
        # Explicit offline SWD capture setup only: a standard (non-narrow)
        # waveform at or below the pre-profile/requested control bit rate.
        half=math.ceil(hz*old_half/old_hz)
        if not 1<=half<=256:raise ValueError('Control divider out of range')
        link=hz/(2*half)
        receive=(1<<18) if link<=30_000_000 else (1<<17) if link<=45_000_000 else 0
        new_cfg=(cfg & ~0xf00fe000)|(((half-1)&15)<<13)|(((half-1)>>4)<<28)|receive
    new_control=(control & ~0x03f03f30)|(destination_source<<4)|(a<<8)|(b<<20)
    return dict(control=new_control, cfg=new_cfg,source=destination_source,
                waveformPreserved=exact,controlRateReduced=not exact,
                oldFclkHz=old_hz, FCLK_Hz=hz, halfPeriod=half,
                oldLinkHz=old_hz/(2*old_half), linkHz=hz/(2*half))


class Fixture:
    def __init__(self, bit, elf, requested, output, *, allow_link_reduction=False):
        self.bit,self.elf=Path(bit).resolve(),Path(elf).resolve()
        self.output=Path(output);self.output.mkdir(exist_ok=False)
        self.requested=requested;self.saved=None;self.report={};self.allow_link_reduction=allow_link_reduction
        if self.bit.parent != self.elf.parent:
            raise ValueError('Explicit bit/ELF pair must share its manifest directory')
        pair=json.loads((self.bit.parent/'manifest.json').read_text(encoding='utf8'))
        for name,path in [('probe.bit',self.bit),('application.elf',self.elf),
                          ('verified_clock.json',self.bit.parent/'verified_clock.json')]:
            expected=pair['files'][name]
            expected=expected['sha256'] if isinstance(expected,dict) else expected
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Pair file hash mismatch: '+name)
        timing=json.loads((self.bit.parent/'verified_clock.json').read_text())
        if requested>timing['FCLK_max_Hz'] or timing['setup_slack_ns']<0 or timing['hold_slack_ns']<0:
            raise ValueError('Requested FCLK exceeds passing routed timing')
        from probe_flash import Session
        from zynq_memory import PhysicalMemory
        self.mem=PhysicalMemory(Session(self.output,Path('E:/Xilinx/SDK/2018.3'),'tcp:127.0.0.1:3121'))
        self.report=dict(requestedFclkHz=requested,timing=timing,flashWrites=False,
                         scope='temporary probe FCLK0 source/dividers and serializer only; PLLs unchanged',restored=False)
        self.save()

    def save(self):
        (self.output/'result.json').write_text(json.dumps(self.report,indent=2)+'\n')

    def idle(self):
        if self.mem.read_words(0x40010004)[0]&1 or self.mem.read_words(0x40040008)[0]&1:
            raise RuntimeError('Serial core or DDR operation still active; no clock change issued')

    def apply(self):
        self.idle()
        clocks=self.mem.read_words(0xf8000100,33)
        control=clocks[28]
        source=(control>>4)&3
        pll=clocks[{0:2,1:2,2:0,3:1}[source]]
        cfg=self.mem.read_words(0x40010008)[0]
        ref=clocks[32]
        destination=2 if self.requested in (133333332,133333333,133333334) else 0
        profile=plan(control,pll,cfg,self.requested,destination_source=destination,
                     destination_pll=clocks[0 if destination==2 else 2],allow_link_reduction=self.allow_link_reduction)
        self.protected={i:clocks[i] for i in (0,1,2,4,5,6,8,9,12,32)}
        self.saved=(control,cfg,ref)
        self.report.update(before=dict(control=control,cfg=cfg,reference=ref),protectedClockRegisters=self.protected,profile=profile)
        self.save()
        self.write(profile['control'],profile['cfg'])
        self.check()
        return profile

    def write(self,control,cfg):
        self.mem.run(f'physwr -force 0xf8000008 0xdf0d\nphyswr -force 0xf8000170 {control:#x}\n'
                     f'physwr -force 0xf8000004 0x767b\nphyswr -force 0x40010008 {cfg:#x}\nputs PROFILE_WRITTEN')

    def check(self):
        if self.saved is None:return
        actual=[self.mem.read_words(a)[0] for a in (0xf8000170,0x40010008,0xf8000180)]
        p=self.report['profile']
        stable=actual==[p['control'],p['cfg'],self.saved[2]]
        clocks=self.mem.read_words(0xf8000100,33)
        stable=stable and all(clocks[i]==v for i,v in self.protected.items())
        self.report.update(after=actual,clockStable=stable);self.save()
        if not stable:raise RuntimeError('Probe clock changed during acceptance')

    def restore(self):
        if self.saved is None:return
        self.idle()
        control,cfg,ref=self.saved
        self.write(control,cfg)
        actual=[self.mem.read_words(a)[0] for a in (0xf8000170,0x40010008,0xf8000180)]
        clocks=self.mem.read_words(0xf8000100,33)
        restored=actual==[control,cfg,ref] and all(clocks[i]==v for i,v in self.protected.items())
        self.report.update(restored=restored,restoreRegisters=actual);self.save()
        if not self.report['restored']:raise RuntimeError('Probe clock restoration mismatch')
