"""Read and validate live WebUSB/WinUSB descriptors, including EP0 stalls.

Does not reset the probe or touch the target. Acquires the normal probe lease.
"""
import argparse
import json
from pathlib import Path
import uuid

import usb.core
import usb.util
from dap_pipeline_bench import open_dap,cmd

URL='https://minichao9901.github.io/zynqlinkPRO/#download'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--hid-name', help='Also verify the HID name and serial with Windows-sized string requests')
    args=parser.parse_args()
    if args.out.exists():parser.error('Use a new output JSON')
    report={'passed':False,'expectedURL':URL,'requests':[]}
    dev,tx,rx=open_dap()
    def control(kind,request,value,index,length):
        data=bytes(dev.ctrl_transfer(kind,request,value,index,length,timeout=3000))
        report['requests'].append({'bmRequestType':kind,'request':request,'value':value,
            'index':index,'length':length,'response':data.hex()})
        return data
    try:
        header=control(0x80,6,0x0f00,0,5)
        total=int.from_bytes(header[2:4],'little')
        bos=control(0x80,6,0x0f00,0,total)
        assert len(bos)==57 and bos[:5]==bytes([5,15,57,0,2]),bos.hex()
        caps=[];offset=5
        while offset<len(bos):
            size=bos[offset];assert size>=4 and offset+size<=len(bos)
            caps.append(bos[offset:offset+size]);offset+=size
        assert len(caps)==2
        web=next(c for c in caps if c[4:20]==uuid.UUID('3408b638-09a9-47a0-8bfd-a0768815b665').bytes_le)
        assert web[20:22]==b'\x00\x01' and web[23]==1
        vendor=web[22]
        url=control(0xc0,vendor,1,2,255)
        assert url[0]==len(url) and url[1:3]==b'\x03\x01'
        actual='https://'+url[3:].decode('ascii')
        assert actual==URL and b'\0' not in url
        for length in [1,3,len(url)]:
            assert control(0xc0,vendor,1,2,length)==url[:length]
        ms=next(c for c in caps if c[4:20]==uuid.UUID('d8dd60df-4589-4cc7-9cd2-659d9e648a9f').bytes_le)
        windows=control(0xc0,ms[26],0,7,178)
        assert len(windows)==178 and b'WINUSB' in windows
        for value,index in [(0,2),(2,2),(1,3)]:
            try:control(0xc0,vendor,value,index,255)
            except usb.core.USBError as error:
                assert error.backend_error_code==-9,repr(error)
                report['requests'].append({'value':value,'index':index,'stalled':True})
            else:raise AssertionError('Malformed GET_URL must stall')
        assert control(0xc0,vendor,1,2,255)==url
        info=cmd(tx,rx,[0,0xff])
        assert len(info)>=4 and info[1]==2
        if args.hid_name:
            device=control(0x80,6,0x0100,0,18)
            serial_index=device[16]
            config_header=control(0x80,6,0x0200,0,9)
            config=control(0x80,6,0x0200,0,int.from_bytes(config_header[2:4],'little'))
            offset=0
            hid_index=0
            while offset<len(config):
                size,kind=config[offset:offset+2]
                assert size>=2 and offset+size<=len(config)
                if kind==4 and size>=9 and config[offset+5]==3:
                    hid_index=config[offset+8]
                    break
                offset+=size
            assert hid_index and serial_index
            for index in (hid_index,serial_index):
                full=control(0x80,6,0x0300|index,0x0409,1026)
                assert full[:2]==bytes([len(full),3])
                assert control(0x80,6,0x0300|index,0x0409,4094)==full
                assert control(0x80,6,0x0300|index,0x0409,2)==full[:2]
                value=full[2:].decode('utf-16-le')
                if index==hid_index:
                    assert value==args.hid_name,value
                    report['hidName']=value
                else:
                    assert value,value
                    report['hidSerial']=value
        report.update(passed=True,url=actual,bosBytes=len(bos),winusbBytes=len(windows),dapPacketSize=int.from_bytes(info[2:4],'little'))
    finally:
        usb.util.dispose_resources(dev)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
