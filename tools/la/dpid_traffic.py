"""Repeat a known DP IDCODE for unambiguous SWD bit/edge alignment."""
import time,struct,argparse
ap=argparse.ArgumentParser()
ap.add_argument("--speed",type=int,default=50000)
ap.add_argument("--seconds",type=float,default=12)
ap.add_argument("--allow-errors",action="store_true")
args=ap.parse_args()
import usb.core,usb.util,libusb_package
d=usb.core.find(idVendor=0x0d28,idProduct=0x0204,backend=libusb_package.get_libusb1_backend())
usb.util.claim_interface(d,0)
def x(b):
 b=bytes(b);d.write(2,b,timeout=3000)
 if len(b)%512==0:d.write(2,b'',timeout=3000)
 return bytes(d.read(0x81,4096,timeout=3000))
x([2,1])
if x(bytes([0x11])+struct.pack('<I',args.speed*1000)) != b'\x11\x00':
 raise RuntimeError('SWCLK request rejected')
x([0x12,56]+[255]*7);x([0x12,16,0x9e,0xe7]);x([0x12,64]+[255]*7+[0]);x([4,0,64,0,0,0])
expected=bytes([6,0,1,1])+struct.pack('<I',0x1ba01477)*256
end=time.monotonic()+args.seconds;n=0
try:
 while time.monotonic()<end:
  r=x([6,0,0,1,2])
  if r!=expected:
   if not args.allow_errors: raise RuntimeError(f'IDCODE mismatch {r[:20].hex()}')
   continue
  n+=1
 print('Verified IDCODE words:',n*256,flush=True)
finally:usb.util.release_interface(d,0)
