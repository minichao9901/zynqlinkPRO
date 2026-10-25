init
halt
echo "DHCSR=[mdw 0xE000EDF0 1]"
echo "PC1=[reg pc]"
sleep 1000
echo "PC2=[reg pc]"
echo "DHCSR2=[mdw 0xE000EDF0 1]"
mww 0x20000000 0xA5A5A5A5
echo "W1=[mdw 0x20000000 2]"
sleep 1000
echo "W2=[mdw 0x20000000 2]"
exit
