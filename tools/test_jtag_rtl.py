"""JTAG protocol plus complete controller/sampler/RTT/packet integration."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
dest=root/'build/jtag_sim';dest.mkdir(parents=True,exist_ok=True)
for top,extra in [
    ('tb_jtag_core',[]),
    ('tb_jtag_pipeline',['swd_core.v','swd_controller.v','swd_batch_engine.v',
      'dap_transfer_block_engine.v','probe_sample_engine.v','probe_rtt_engine.v','probe_stream_engine.v']),
]:
    files=[root/'fpga/rtl'/s for s in ['jtag_shift.v','jtag_core.v']+extra]
    files+=[root/'fpga/sim/jtag_dp_model.sv',root/'fpga/sim'/f'{top}.sv']
    if extra:files+=[root/'fpga/sim/xpm_memory_tdpram.sv',root/'fpga/sim/tb_packet_axi.sv']
    exe=dest/(top+'.vvp')
    subprocess.run(['iverilog','-g2012','-s',top,'-o',str(exe),*map(str,files)],check=True)
    r=subprocess.run(['vvp',str(exe)],capture_output=True,text=True,timeout=90)
    (dest/(top+'.log')).write_text(r.stdout+r.stderr)
    print(r.stdout+r.stderr,end='')
    assert r.returncode==0
    if extra:
        for args,suffix in [(['+late'],'_late'),(['+late','+q1'],'_q1_late')]:
            r=subprocess.run(['vvp',str(exe),*args],capture_output=True,text=True,timeout=90)
            (dest/(top+suffix+'.log')).write_text(r.stdout+r.stderr)
            print(r.stdout+r.stderr,end='')
            assert r.returncode==0
