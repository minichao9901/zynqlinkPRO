"""Record the exact pair supplied to a probe benchmark, never a fixed Git tag."""
import hashlib
from pathlib import Path
import subprocess


def live_clock_snapshot():
    """Observe PS/PL clock registers without suspending the DAP target owner."""
    import re
    try:
        from .jtag_internal_trace import run
    except ImportError:
        from jtag_internal_trace import run
    # CPU-context mrd can suspend/cache-synchronize the live forwarding owner.
    # Select the APU MEM-AP explicitly, exactly as PhysicalMemory does, so this
    # observer does not steal CPU execution while RTT/CDC is streaming.
    output=run('targets -set -filter {name =~ "APU"}\n'
               'puts [format "LIVECLK %08X %08X %08X %08X %08X %08X %08X %08X" [mrd -address-space AP0 -force -value 0xf8000170] [mrd -address-space AP0 -force -value 0xf8000108] [mrd -address-space AP0 -force -value 0x40010008] [mrd -address-space AP0 -force -value 0x40010098] [mrd -address-space AP0 -force -value 0x40010080] [mrd -address-space AP0 -force -value 0xf8000100] [mrd -address-space AP0 -force -value 0xf8000104] [mrd -address-space AP0 -force -value 0xf800025c]]')
    match=re.search(r'LIVECLK '+r'([0-9A-Fa-f]{8}) '*7+r'([0-9A-Fa-f]{8})',output)
    assert match,output
    control,io_pll,cfg,timing,route,arm_pll,ddr_pll,boot=[int(v,16) for v in match.groups()]
    try:from .zynq_clock import fclk_hz
    except ImportError:from zynq_clock import fclk_hz
    source=(control>>4)&3
    pll={0:io_pll,1:io_pll,2:arm_pll,3:ddr_pll}[source]
    fclk=fclk_hz(control,pll,boot)
    return dict(FCLK_Hz=fclk,cfg=hex(cfg),waveform=swd_clock_details(fclk,cfg),
                clockSource=source,clockControl=control,sourcePllControl=pll,
                frequencyBasis='read-back PLL/source/divisors, rounded PS_REF; not a frequency-counter measurement',
                JTAG_sampling_mode=timing&17,RISC_V_SBA_enabled=bool(route&4),
                actual_link_Hz=swd_clock_details(fclk,cfg)['SWCLK_Hz'],
                clock_observation='physical MEM-AP0 read; no CPU debug context or DAP command during stream')


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
