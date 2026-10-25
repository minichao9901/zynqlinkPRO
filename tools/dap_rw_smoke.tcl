init
halt
echo "PC=[reg pc]"
mww 0x20000000 0x11223344
mww 0x20000004 0x55667788
echo "READBACK1=[mdw 0x20000000 4]"
mww 0x20000000 0x99aabbcc
echo "READBACK2=[mdw 0x20000000 4]"
echo "SPEED_NOW=[adapter speed]"
exit
