"""Extract only one probe's completed CDC URBs from USBPcap LINKTYPE 249.

Order by IN request submission; record completion reordering and truncated tail.
Format: https://desowin.org/usbpcap/captureformat.html
"""
import argparse,struct,json,hashlib
from pathlib import Path
def extract(path,bus,device,endpoint=0x83,expected=None):
    raw=path.read_bytes();assert raw[:4]==b'\xd4\xc3\xb2\xa1'and struct.unpack_from('<I',raw,20)[0]==249
    at=24;pending={};finished=[];index=0;unknown=[];errors=[]
    while at+16<=len(raw):
        sec,usec,size,original=struct.unpack_from('<4I',raw,at)
        if at+16+size>len(raw):break
        packet=raw[at+16:at+16+size];at+=16+size;index+=1
        if len(packet)<27:continue
        h,irp,status,function,info,b,d,ep,transfer,n=struct.unpack_from('<HQIHBHHBBI',packet)
        if(b,d,ep)!=(bus,device,endpoint):continue
        if not info&1:pending[irp]=index;continue
        seq=pending.pop(irp,None)
        if status:errors.append(dict(index=index,status=hex(status)))
        if n:
            data=packet[h:h+n];assert len(data)==n
            if seq is None:unknown.append(index);seq=index
            finished.append((seq,index,sec+usec/1e6,data,status))
    ordered=sorted(finished)
    data=b''.join(r[3]for r in ordered)
    successful=b''.join(r[3]for r in ordered if not r[4])
    stats=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),records=index,completedDataUrbs=len(ordered),
        successfulBytes=len(successful),successful_sha256=hashlib.sha256(successful).hexdigest(),
        failedPayloadBytes=len(data)-len(successful),
        reorderedCompletions=sum(a[1]!=b[1]for a,b in zip(finished,ordered)),
        errors=errors,unknownSubmissions=unknown,incompleteTailBytes=len(raw)-at,
        transfers=[dict(submit=r[0],complete=r[1],time=r[2],bytes=len(r[3]),status=hex(r[4]),firstBytes=r[3][:12].hex())for r in ordered])
    if expected is not None:stats.update(matchesWeb=data==expected,matchesWebSuccessfulOnly=successful==expected,webBytes=len(expected))
    return data,stats
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pcap',type=Path);p.add_argument('--bus',type=int,default=3);p.add_argument('--device',type=int,default=8);p.add_argument('--out',type=Path,required=True);p.add_argument('--expected',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);data,stats=extract(a.pcap,a.bus,a.device,expected=a.expected.read_bytes()if a.expected else None)
    (a.out/'cdc.bin').write_bytes(data)
    (a.out/'result.json').write_text(json.dumps(stats,indent=2)+'\n');print({k:v for k,v in stats.items()if k!='transfers'})
if __name__=='__main__':main()
