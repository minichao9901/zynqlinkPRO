"""Record the exact pair supplied to a probe benchmark, never a fixed Git tag."""
import hashlib
from pathlib import Path
import subprocess


def live_clock_snapshot():
    """Observe PS/PL clock registers without suspending the DAP target owner."""
    import re
    from jtag_internal_trace import run
    output=run('puts [format "LIVECLK %08X %08X %08X %08X %08X" [mrd -force -value 0xf8000170] [mrd -force -value 0xf8000108] [mrd -force -value 0x40010008] [mrd -force -value 0x40010098] [mrd -force -value 0x40010080]]')
    match=re.search(r'LIVECLK '+r'([0-9A-Fa-f]{8}) '*4+r'([0-9A-Fa-f]{8})',output)
    assert match,output
    control,pll,cfg,timing,route=[int(v,16) for v in match.groups()]
    assert ((control>>4)&3) in (0,1) and not pll&16,'Unexpected PLL source/bypass'
    fclk=33333333*((pll>>12)&127)//((control>>8)&63)//((control>>20)&63)
    return dict(FCLK_Hz=fclk,cfg=hex(cfg),waveform=swd_clock_details(fclk,cfg),
                JTAG_sampling_mode=timing&17,RISC_V_SBA_enabled=bool(route&4),
                actual_link_Hz=swd_clock_details(fclk,cfg)['SWCLK_Hz'],
                clock_observation='PS JTAG register read; no DAP command during stream')


def swd_clock_details(fclk_hz, cfg):
    """Decode the realized SWD waveform, including the extended divider."""
    half_cycles=1+((cfg>>13)&15)+(((cfg>>28)&15)<<4)
    short=bool(cfg&(1<<19))
    return dict(SWCLK_Hz=fclk_hz/(2*half_cycles),half_period_fclk=half_cycles,
                short_high=short,intended_high_ns=1e9*(1 if short else half_cycles)/fclk_hz)


def provenance(bit=None, elf=None):
    root=Path(__file__).resolve().parents[1]
    result={'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'git_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())}
    for label,path in [('bit',bit),('elf',elf)]:
        if path:
            path=Path(path).resolve()
            result[label]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result
