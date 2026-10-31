"""Package an existing build for probe-flash; does not build, load, flash or claim acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from build_probe_boot import partitions


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--loader-dir',type=Path,required=True,help='output directory of build_probe_boot.py')
    p.add_argument('--bit',type=Path,required=True)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True,help='new directory; refuses overwrite')
    p.add_argument('--ps-init',type=Path,required=True,help='matching QSPI-enabled ps7_init.tcl')
    p.add_argument('--elf50',type=Path)
    p.add_argument('--timing-report',type=Path)
    p.add_argument('--utilization-report',type=Path)
    a=p.parse_args()
    source=a.loader_dir.resolve()
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    pair=manifest.get('input_pair',{})
    if pair!={'bit_sha256':digest(a.bit),'elf_sha256':digest(a.elf)}:
        p.error('BOOT build input pair does not match the supplied bit/ELF')
    init_hashes=[value for name,value in manifest['source_sha256'].items()
                 if name.replace('\\','/').endswith('/hardware/ps7_init.tcl')]
    if init_hashes!=[digest(a.ps_init)]:p.error('PS initialization does not match the loader build')
    required=['BOOT.bin','BOOT.bif','fsbl_stage0.elf','fsbl_stage2.elf',
              'fsbl_stage2.bin','fsbl_programmer.elf','qspi_read.elf']
    for name in required:
        if digest(source/name)!=manifest['files'][name]:p.error('Loader artifact SHA mismatch: '+name)
    partitions(source/'BOOT.bin')  # verify headers, partition bounds and MD5
    if (source/'BOOT.bin').stat().st_size>=16<<20:p.error('BOOT image exceeds first 16MiB')
    destination=a.output_dir.resolve();destination.mkdir(parents=True,exist_ok=False)
    for name in required:shutil.copyfile(source/name,destination/name)
    shutil.copyfile(source/'manifest.json',destination/'build_manifest.json')
    shutil.copyfile(a.bit,destination/'probe.bit');shutil.copyfile(a.elf,destination/'application.elf')
    shutil.copyfile(a.ps_init,destination/'ps7_init.tcl')
    for path,name in [(a.elf50,'application_50.elf'),(a.timing_report,'timing.rpt'),
                      (a.utilization_report,'utilization.rpt')]:
        if path:shutil.copyfile(path,destination/name)
    (destination/'.gitattributes').write_text('* -text -whitespace\n',encoding='ascii')
    # Keep the original BIF as provenance; this additional recipe survives relocation.
    (destination/'rebuild.bif').write_text('the_ROM_image:\n{\n [bootloader] fsbl_stage0.elf\n'
        ' [checksum=md5] probe.bit\n [checksum=md5] application.elf\n}\n',encoding='ascii')
    files={path.name:digest(path) for path in destination.iterdir() if path.is_file() and path.name!='.gitattributes'}
    report=dict(files=files,device='xc7z020clg400-2',input_pair=pair,
                source_revision=manifest['source_revision'],boot_validation='NOT PERFORMED: packaging only',
                note='Run board acceptance and record results before marking this package accepted.')
    (destination/'flash_manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(output_dir=str(destination),BOOT_sha256=files['BOOT.bin'],validation='not performed'),indent=2))


if __name__=='__main__':main()
