"""Record the exact pair supplied to a probe benchmark, never a fixed Git tag."""
import hashlib
from pathlib import Path
import subprocess


def provenance(bit=None, elf=None):
    root=Path(__file__).resolve().parents[1]
    result={'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'git_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())}
    for label,path in [('bit',bit),('elf',elf)]:
        if path:
            path=Path(path).resolve()
            result[label]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result
