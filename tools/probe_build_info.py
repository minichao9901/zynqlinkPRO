"""Record the exact pair supplied to a probe benchmark, never a fixed Git tag."""
import hashlib
from pathlib import Path
import subprocess


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
