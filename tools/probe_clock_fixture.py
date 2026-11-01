"""Temporary, STA-bounded FCLK0 profile for offline board acceptance.

The serializer divider changes with FCLK0 to preserve the existing SWD rate.
No target RCC, PLL, Flash, firmware policy, or independent FCLK1 is changed.
"""
import hashlib
import json
from pathlib import Path


def plan(control, pll, cfg, requested):
    if ((control >> 4) & 3) != 0 or pll & 0x13:
        raise ValueError('Requires running IO PLL source')
    pll_hz = 33333333 * ((pll >> 12) & 127)
    if not ((control >> 8) & 63) or not ((control >> 20) & 63) or requested<=0:
        raise ValueError('Invalid clock divisor or requested rate')
    old_hz = pll_hz // ((control >> 8) & 63) // ((control >> 20) & 63)
    old_half = 1 + ((cfg >> 13) & 15) + (((cfg >> 28) & 15) << 4)
    if cfg & (1 << 19):
        raise ValueError('Short high-pulse profile cannot preserve its waveform')
    choices = [(pll_hz // a // b, a, b) for a in range(1,64) for b in range(1,64)
               if pll_hz // a // b <= requested]
    hz, a, b = max(choices)
    half = round(hz * old_half / old_hz)
    # Integer register readouts can differ by one Hz due to floor operations.
    if not 1 <= half <= 256 or abs(hz * old_half - old_hz * half) > max(half,old_half):
        raise ValueError('Requested FCLK cannot preserve the external link frequency')
    new_cfg = (cfg & ~0xf001e000) | (((half-1) & 15) << 13) | (((half-1) >> 4) << 28)
    return dict(control=1 | (a << 8) | (b << 20), cfg=new_cfg,
                oldFclkHz=old_hz, FCLK_Hz=hz, halfPeriod=half,
                oldLinkHz=old_hz/(2*old_half), linkHz=hz/(2*half))


class Fixture:
    def __init__(self, bit, elf, requested, output):
        self.bit,self.elf=Path(bit).resolve(),Path(elf).resolve()
        self.output=Path(output);self.output.mkdir(exist_ok=False)
        self.requested=requested;self.saved=None;self.report={}
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
                         scope='temporary probe FCLK0 and serializer divider only',restored=False)
        self.save()

    def save(self):
        (self.output/'result.json').write_text(json.dumps(self.report,indent=2)+'\n')

    def idle(self):
        if self.mem.read_words(0x40010004)[0]&1 or self.mem.read_words(0x40040008)[0]&1:
            raise RuntimeError('Serial core or DDR operation still active; no clock change issued')

    def apply(self):
        self.idle()
        control=self.mem.read_words(0xf8000170)[0]
        pll=self.mem.read_words(0xf8000108)[0]
        cfg=self.mem.read_words(0x40010008)[0]
        ref=self.mem.read_words(0xf8000180)[0]
        profile=plan(control,pll,cfg,self.requested)
        self.saved=(control,cfg,ref)
        self.report.update(before=dict(control=control,cfg=cfg,reference=ref),profile=profile)
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
        self.report.update(after=actual,clockStable=stable);self.save()
        if not stable:raise RuntimeError('Probe clock changed during acceptance')

    def restore(self):
        if self.saved is None:return
        self.idle()
        control,cfg,ref=self.saved
        self.write(control,cfg)
        actual=[self.mem.read_words(a)[0] for a in (0xf8000170,0x40010008,0xf8000180)]
        self.report.update(restored=actual==[control,cfg,ref],restoreRegisters=actual);self.save()
        if not self.report['restored']:raise RuntimeError('Probe clock restoration mismatch')
