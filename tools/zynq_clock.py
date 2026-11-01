"""Read-only Zynq-7000 FCLK arithmetic, shared by acceptance tools."""
PLL_REGISTERS={0:0xf8000108,1:0xf8000108,2:0xf8000100,3:0xf8000104}


def pll_hz(control, boot_mode=0):
    if control&3:raise ValueError('PLL reset or powered down')
    bypass=boot_mode&16 if control&8 else control&16
    return 33333333 if bypass else 33333333*((control>>12)&127)


def fclk_hz(control, pll, boot_mode=0):
    a,b=(control>>8)&63,(control>>20)&63
    if not a or not b:raise ValueError('Zero FCLK divisor')
    return pll_hz(pll,boot_mode)//a//b


def snapshot(read):
    control=read(0xf8000170)[0]
    source=(control>>4)&3
    pll=read(PLL_REGISTERS[source])[0]
    boot=read(0xf800025c)[0]
    return dict(control=control,source=source,pll=pll,bootMode=boot,
                FCLK_Hz=fclk_hz(control,pll,boot))
