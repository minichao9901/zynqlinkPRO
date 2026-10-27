"""Query/apply the experimental SWD timing profile (vendor 0x90).

Connect the DAP first, then apply a profile. No board access occurs on import.
Offsets are FCLK cycles within a capture half phase, not nanoseconds.
"""
import argparse
import json
import struct
from dap_pipeline_bench import open_dap,cmd

FIELDS=['control','half_q','swj_half_q','ack_sample','data_sample','ack_half_q','turn_half_q','legacy_cfg']
SOURCES={'legacy':0,'q1':1,'q2':2,'raw':3}

def decode(reply):
    if len(reply)!=44 or reply[0]!=0x90:
        raise RuntimeError('Unexpected timing response: '+reply.hex())
    fclk,status,*words=struct.unpack('<10I',reply[4:])
    result=dict(zip(FIELDS,words));result.update(fclk_hz=fclk,status=status,
        enabled=bool(words[0]&1),version=reply[2],command_ok=reply[1]==0,
        busy=bool(status&1),error=(status>>8)&255,epoch=status>>16)
    q=words[1] if words[0]&1 else ((((words[7]>>13)&15)+1)<<16)
    result['average_tck_hz']=fclk*65536/(2*q) if q else 0
    return result

def sample_word(offset,source,previous):
    value=previous
    if offset is not None:
        number=65536 if offset=='end' else int(offset,0)
        if offset!='end' and not 0<=number<=65535:
            raise ValueError('Sample offset must be 0..65535, or end')
        value=(previous&(3<<17))|number
    if source is not None:value=(value&~(3<<17))|(SOURCES[source]<<17)
    return value

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['query','apply','disable'])
    ap.add_argument('--control',type=int,choices=[0,1],default=1,help='apply with 1=extended, 0=legacy')
    ap.add_argument('--fclk',type=int,default=0,help='optional FCLK ceiling, Hz (500k..120M)')
    for name in ['swj-half-q','ack-half-q','turn-half-q','legacy-cfg']:
        ap.add_argument('--'+name,type=lambda s:int(s,0))
    frequency=ap.add_mutually_exclusive_group()
    frequency.add_argument('--half-q',type=lambda s:int(s,0))
    frequency.add_argument('--hz',type=int,help='calculate ceil Q16 half period from actual FCLK')
    ap.add_argument('--idle',type=int,choices=range(16))
    ap.add_argument('--ack-hold',type=int,choices=range(8))
    ap.add_argument('--turn-extra',type=int,choices=range(4))
    ap.add_argument('--wait-data-phase',type=int,choices=[0,1])
    ap.add_argument('--legacy-phase',choices=['q1','q2'])
    for name in ['ack','data']:
        ap.add_argument('--'+name+'-offset',help='end, or a zero-based FCLK cycle')
        ap.add_argument('--'+name+'-source',choices=SOURCES)
    args=ap.parse_args()
    dev,out,inp=open_dap()
    try:
        current=decode(cmd(out,inp,[0x90,0]))
        if current['version']!=1:raise RuntimeError('SWT1 timing hardware/firmware required')
        if args.action=='apply':
            if args.hz and args.fclk:ap.error('--hz requires current FCLK; set FCLK in a separate apply first')
            words=[current[n] for n in FIELDS];words[0]=args.control
            for i,name in enumerate(FIELDS):
                if i and getattr(args,name,None) is not None:words[i]=getattr(args,name)
            if args.hz:
                if args.hz<=0:ap.error('--hz must be positive')
                denominator=2*args.hz;words[1]=(current['fclk_hz']*65536+denominator-1)//denominator
            words[3]=sample_word(args.ack_offset,args.ack_source,words[3])
            words[4]=sample_word(args.data_offset,args.data_source,words[4])
            for value,shift,width in [(args.idle,4,4),(args.ack_hold,25,3),
                    (args.turn_extra,23,2),(args.wait_data_phase,8,1),
                    (None if args.legacy_phase is None else int(args.legacy_phase=='q1'),17,1)]:
                if value is not None:words[7]=(words[7]&~(((1<<width)-1)<<shift))|(value<<shift)
            packet=bytes([0x90,1])+struct.pack('<9I',args.fclk,*words)
            current=decode(cmd(out,inp,packet))
        elif args.action=='disable':current=decode(cmd(out,inp,[0x90,2]))
        print(json.dumps(current,indent=2))
        if not current['command_ok']:raise SystemExit('Timing command rejected')
    finally:
        import usb.util
        usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)

if __name__=='__main__':main()
