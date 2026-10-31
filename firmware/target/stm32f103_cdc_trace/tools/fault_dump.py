#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fault_dump.py —— 读 Cortex-M3 的 HardFault 现场（栈帧 + CFSR/HFSR/MMFAR/BFAR）

用途：固件跑飞进了 HardFault_Handler 的死循环时，PC 只指向那个 `b .`，
看不出真正出错的位置。异常发生时 CPU 会把 8 个字压进栈，其中第 7 个字就是
出错时的 PC（栈帧布局：R0 R1 R2 R3 R12 LR PC xPSR）。
本脚本从当前 SP 附近扫描出这个栈帧，并打印故障状态寄存器。

用法：
  python fault_dump.py --target stm32f103cb
  python fault_dump.py --target stm32f103cb --sp 0x20004fd0     # 手动指定栈指针
"""
import argparse
import sys
import threading
import time

WATCHDOG_S = 60

# Cortex-M3 故障寄存器
CFSR = 0xE000ED28   # 可拆成 MMFSR(0xE000ED28) / BFSR(0xE000ED29) / UFSR(0xE000ED2A)
HFSR = 0xE000ED2C
DFSR = 0xE000ED30
MMFAR = 0xE000ED34
BFAR = 0xE000ED38

# HardFault 状态寄存器位说明（节选常用）
CFSR_BITS = [
    (0, "IACCVIOL  取指访问违例"), (1, "DACCVIOL  数据访问违例"),
    (3, "MUNSTKERR 出栈错误"), (4, "MSTKERR   入栈错误"),
    (7, "MMARVALID MMFAR 有效"),
    (8, "IBUSERR   总线取指错误"), (9, "PRECISERR 精确总线错误"),
    (10, "IMPRECISERR 非精确总线错误"), (12, "STKERR 入栈总线错误"),
    (13, "UNSTKERR 出栈总线错误"), (15, "BFARVALID BFAR 有效"),
    (16, "UNDEFINSTR 未定义指令"), (17, "INVSTATE 非法状态(如 ARM 态)"),
    (18, "INVPC     非法 PC"), (19, "NOCP 无协处理器"),
    (24, "UNALIGNED 非对齐访问"), (25, "DIVBYZERO 除零"),
]


def _wd():
    time.sleep(WATCHDOG_S)
    print("[watchdog] 超时", file=sys.stderr)
    sys.exit(9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="stm32f103cb")
    ap.add_argument("--freq", type=int, default=1_000_000)
    ap.add_argument("--sp", type=lambda s: int(s, 0), default=None)
    args = ap.parse_args()
    threading.Thread(target=_wd, daemon=True).start()

    from pyocd.core.helpers import ConnectHelper
    s = ConnectHelper.session_with_chosen_probe(
        target_override=args.target, frequency=args.freq, options={"auto_unlock": False})
    if s is None:
        print("连不上探针", file=sys.stderr)
        return 2

    with s:
        t = s.target
        if t.get_state() != t.State.HALTED:
            t.halt()

        cfsr = t.read32(CFSR)
        hfsr = t.read32(HFSR)
        dfsr = t.read32(DFSR)
        mmfar = t.read32(MMFAR)
        bfar = t.read32(BFAR)

        print("=== 故障状态寄存器 ===")
        print(f"  CFSR  = 0x{cfsr:08x}   (MMFSR=0x{cfsr & 0xFF:02x} BFSR=0x{(cfsr >> 8) & 0xFF:02x} UFSR=0x{(cfsr >> 16) & 0xFFFF:04x})")
        print(f"  HFSR  = 0x{hfsr:08x}   VECTTBL={(hfsr >> 1) & 1} FORCED={(hfsr >> 30) & 1} DEBUGEVT={(hfsr >> 31) & 1}")
        print(f"  DFSR  = 0x{dfsr:08x}")
        print(f"  MMFAR = 0x{mmfar:08x}")
        print(f"  BFAR  = 0x{bfar:08x}")
        hits = [name for bit, name in CFSR_BITS if cfsr & (1 << bit)]
        print("  置位的故障位：" + ("；".join(hits) if hits else "（无）"))

        sp = args.sp if args.sp is not None else t.read_core_register("sp")
        print(f"\n=== 异常栈帧搜索（从 SP=0x{sp:08x} 附近）===")
        found = False
        for off in range(0, 0x120, 4):
            addr = (sp + off) & 0xFFFFFFFC
            try:
                words = [t.read32(addr + i * 4) for i in range(8)]
            except Exception:
                continue
            r0, r1, r2, r3, r12, lr, pc, xpsr = words
            # 栈帧特征：xPSR 的 T 位(bit24)通常为 1；PC 落在 Flash/RAM 合理区间
            looks_like_frame = (xpsr & (1 << 24)) != 0 and 0x08000000 <= pc <= 0x08080000
            if looks_like_frame:
                print(f"  候选栈帧 @0x{addr:08x}:")
                print(f"    R0=0x{r0:08x} R1=0x{r1:08x} R2=0x{r2:08x} R3=0x{r3:08x}")
                print(f"    R12=0x{r12:08x} LR=0x{lr:08x} PC=0x{pc:08x} xPSR=0x{xpsr:08x}")
                print(f"    >>> 出错指令地址 = 0x{pc:08x}（用 objdump 反汇编这个地址即可定位）")
                found = True
                break
        if not found:
            print("  未找到明显的异常栈帧（栈可能已被破坏，或 SP 不在栈帧上）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
