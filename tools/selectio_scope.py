"""Validate native HSS v2 frames and optionally write a timestamped CSV."""
import csv
import struct
from contextlib import ExitStack
from pathlib import Path


FORMATS=("B","b","H","h","I","i","f","d")


def export_scope(record,csv_path=None,expected=None):
    record=Path(record)
    groups=packets=missing=0
    previous=None;extended=0
    definition=None;stat=None
    created=False
    try:
        with ExitStack() as files:
            source=files.enter_context(record.open("rb"))
            sink=files.enter_context(Path(csv_path).open("x",encoding="utf8",newline="")) if csv_path else None
            created=sink is not None
            writer=csv.writer(sink) if sink else None
            while frame:=source.read(512):
                if len(frame)!=512:raise ValueError("truncated HSS frame")
                magic,version,kind,seq,stamp,n,aux=struct.unpack_from("<HBBIIHH",frame)
                if magic!=0x4a53 or version!=2 or seq!=packets&0xffffffff:
                    raise ValueError(f"HSS identity or sequence mismatch at frame {packets}")
                packets+=1
                if kind==1:
                    if definition is not None or seq!=0:raise ValueError("unexpected HSS definition")
                    hz,ticks,flags,channels,spans=struct.unpack_from("<IIHBB",frame,16)
                    if not ticks or not 1<=channels<=8:raise ValueError("invalid sample plan")
                    fields=[];fmts=[]
                    for i in range(channels):
                        addr,size,code=struct.unpack_from("<IBB",frame,28+8*i)
                        if code>=len(FORMATS) or size not in (1,2,4,8):raise ValueError("invalid variable shape")
                        fmt=FORMATS[code]
                        if struct.calcsize("<"+fmt)!=size:
                            # Older native fixtures used type 0 for any unsigned width.
                            if code!=0:raise ValueError("type and byte width disagree")
                            fmt={1:"B",2:"H",4:"I",8:"Q"}[size]
                        fmts.append(fmt);fields.append(dict(address=hex(addr),size=size,type=code))
                    layout=struct.Struct("<"+"".join(fmts))
                    definition=dict(link_hz=hz,period_ticks=ticks,flags=flags,variables=fields)
                    if writer:writer.writerow(["tick_24mhz",*(f["address"] for f in fields)])
                elif kind==2:
                    if not definition or stat is not None or not n or aux!=n*layout.size or aux>496:
                        raise ValueError("invalid HSS DATA length or ordering")
                    if previous is None:extended=stamp
                    else:
                        first,num=previous
                        delta=(stamp-first)&0xffffffff
                        gap=delta-num*ticks
                        if gap<0 or gap%ticks:raise ValueError("invalid HSS time grid")
                        missing+=gap//ticks;extended+=delta
                    raw=frame[16:16+aux]
                    if expected is not None and raw!=expected*n:raise ValueError(f"HSS value mismatch in frame {seq}")
                    if writer:
                        for i,values in enumerate(layout.iter_unpack(raw)):writer.writerow((extended+i*ticks,*values))
                    previous=(stamp,n);groups+=n
                elif kind==3:
                    if not definition or stat is not None:raise ValueError("unexpected HSS STAT")
                    produced,skipped,sequence=struct.unpack_from("<III",frame,16)
                    errors=struct.unpack_from("<H",frame,30)[0]
                    stat=dict(produced=produced,skipped=skipped,frame_count=sequence,read_errors=errors)
                else:raise ValueError(f"unknown HSS frame kind {kind}")
        if not stat or stat["produced"]!=groups or stat["frame_count"]!=packets or stat["read_errors"]:
            raise ValueError(f"HSS STOP totals differ: groups={groups}, frames={packets}, STAT={stat}")
        return dict(definition=definition,packets=packets,groups=groups,timeline_skips=missing,stat=stat)
    except BaseException:
        if created:
            Path(csv_path).unlink(missing_ok=True)
        raise
