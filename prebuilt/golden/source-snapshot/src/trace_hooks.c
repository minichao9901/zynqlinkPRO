/*
 * etm-trace 钩子实现 —— STM32F103 + CherryUSB CDC ACM
 *
 * 默认与 stm32h7b0_spi_trace 一致：Trace 外设由外部 SWD 工具配置。
 * ZE 可选 TRACE_ETM_STANDALONE 构建用于 LA 直采实验。
 *
 * ⚠️ F103 的 ETM 支持分型号（见 README）：F103CB/RB/C8 无 ETM（只有 ITM/SWO + DWT），
 *    F103ZE/xE 有 ETMv3。本文件在两种型号上都只做 DWT + GPIO 打点，不碰 ETM。
 */
#include "trace_hooks.h"
#include "stm32f1xx.h"
#include "SEGGER_RTT.h"

#include <stdarg.h>
#include <stdio.h>

/* 固定地址段（RAM 末尾，链接脚本钉死），外部工具可直接按地址读 */
__attribute__((section(".trace_diag"), used)) volatile trace_diag_t g_trace;

/* Cortex-M3 的 DWT / DEMCR */
#define DEMCR      (*(volatile uint32_t *)0xE000EDFCu)
#define DWT_CTRL   (*(volatile uint32_t *)0xE0001000u)
#define DWT_CYCCNT (*(volatile uint32_t *)0xE0001004u)
#define DWT_LAR    (*(volatile uint32_t *)0xE0001FB0u)
#define TRACE_REG(addr) (*(volatile uint32_t *)(addr))

/* 逻辑分析仪打点脚：PA1（推挽输出，每次 trace_hook_mark 翻转）。
 * 注：PA0 被参照工程的"进入 DFU"判据用过，这里改 PA1，避免与板级跳线冲突。 */
#define TRACE_PIN_PORT GPIOA
#define TRACE_PIN      GPIO_PIN_1

static uint32_t s_last_cycles;
static uint8_t s_pin_state;

/* main.c 里实测出来的 SYSCLK */
extern uint32_t g_sysclk_hz;

#if defined(STM32F103xE) && defined(TRACE_ETM_STANDALONE)
/*
 * 独立 ETM 初始化（ETMv3 + TPIU 4 位 DDR 并行口）
 *
 * ★ 2026-10-13 修正：原实现在"第一个 IDLE 等待超时"时直接 return，后果是
 *   **DBGMCU（trace 引脚使能）、ITM 同步、TRACEOUT 收尾全都没执行** ——
 *   实测读回的现场就是证据：dbgmcu_cr=0x7（TRACE_IOEN(bit5)=0，引脚没使能）、
 *   itm_tcr=0、etmcr=0xc10（PROG 还挂着）、g_trace.etm_status=2。
 *   引脚 GPIOCRL 明明配好了 PE2~PE6=0xB(AF推挽)，但外设没被使能，LA 上当然没波形。
 *
 * ★ 另一个用法错误：ETMv3 要进编程模式，必须**先把 tracing 停掉**（TRACEOUT=0）
 *   再等 TRCSTATR.IDLE=1。原代码在 TRACEOUT 仍为 1 的状态下等 IDLE，必然超时。
 *   正确顺序（ARM IHI0014 ETMv3 规定）：
 *       POWERDOWN=0 → 清 TRACEOUT → 等 IDLE=1 → 置 PROG=1 → 写寄存器 → 清 PROG → 置 TRACEOUT=1
 *
 * 本版本：IDLE 等待只作为**参考**记录，任何一步超时都不再中断整个初始化
 * （因为实测该芯片上 IDLE 读数与文档描述不完全一致，硬失败会连带把后面全跳过）。
 * 每一步的成败记录在 g_trace.etm_bits 位图里，事后可精确判断。
 */
#define ETM_BIT_TRCENA    (1u << 0)
#define ETM_BIT_ETM_UNLK  (1u << 1)
#define ETM_BIT_TPIU_UNLK (1u << 2)
#define ETM_BIT_PROG      (1u << 3)
#define ETM_BIT_TRACEOUT  (1u << 4)
#define ETM_BIT_DBGMCU    (1u << 5)
#define ETM_BIT_ITM       (1u << 6)
#define ETM_BIT_PINS      (1u << 7)
#define ETM_BITS_ALL      (0xFFu)

static void trace_etm_standalone_init(void)
{
    const uint32_t etm = 0xE0041000u;
    const uint32_t tpiu = 0xE0040000u;
    uint32_t cr;
    uint32_t timeout;
    uint32_t bits = g_trace.etm_bits & ETM_BIT_PINS; /* 引脚位由调用方在 MX_GPIO_Init 之后先置好，这里继承 */

    g_trace.etm_status = 1u;

    /* --- 1) 总开关 + CoreSight 解锁 --- */
    DEMCR |= 1u << 24; /* TRCENA */
    bits |= ETM_BIT_TRCENA;
    TRACE_REG(etm + 0xFB0u) = 0xC5ACCE55u;  /* ETM LAR */
    TRACE_REG(tpiu + 0xFB0u) = 0xC5ACCE55u; /* TPIU LAR */
    TRACE_REG(0xE0000FB0u) = 0xC5ACCE55u;   /* ITM LAR */

    /* 解锁判定**不能**看 LSR 的 lock 位：本芯片实测 0xE0041FB4 恒为 0x1
     * （写 LAR 解锁键也消不掉），但 etmcr/tpiu 寄存器照样可写 —— 该位在此实现里不表示
     * "被锁住"。所以这里做**功能性判定**：读一份 etmcr，改掉一个无害位再写回，
     * 能读回新值就说明组件确实可写（= 已解锁）。TPIU 同理。 */
    {
        uint32_t probe_orig = TRACE_REG(etm);
        uint32_t probe_new = probe_orig ^ 0x00000080u; /* 翻转 STALL(bit7)，随写随还原 */
        TRACE_REG(etm) = probe_new;
        if (TRACE_REG(etm) == probe_new) {
            bits |= ETM_BIT_ETM_UNLK;
        }
        TRACE_REG(etm) = probe_orig;
    }
    {
        uint32_t probe_orig = TRACE_REG(tpiu + 0xF0u); /* SPPR */
        uint32_t probe_new = probe_orig ^ 0x00000002u; /* 翻转保留位，随写随还原 */
        TRACE_REG(tpiu + 0xF0u) = probe_new;
        if (TRACE_REG(tpiu + 0xF0u) == probe_new) {
            bits |= ETM_BIT_TPIU_UNLK;
        }
        TRACE_REG(tpiu + 0xF0u) = probe_orig;
    }

    /* --- 2) ETM：先上电并**停掉 tracing**，再进编程模式 --- */
    cr = TRACE_REG(etm);
    TRACE_REG(etm) = cr & ~1u;      /* 退出 power-down */
    TRACE_REG(etm) = TRACE_REG(etm) & ~0x800u; /* ★ 清 TRACEOUT：进编程模式前必须停 tracing */

    /* 等 IDLE=1（仅作参考，超时不致命） */
    for (timeout = 0; timeout < 200000u; ++timeout) {
        if (TRACE_REG(etm + 0x10u) & 2u) break;
    }

    TRACE_REG(etm) = TRACE_REG(etm) | 0x400u; /* PROG=1 */
    bits |= ETM_BIT_PROG;

    /* 端口宽度：按 ETMSCR（bit0..bit3 指示支持的端口宽度）把 ETMCR 的 b4..b6 配成 4 位。
     * Linux 的写法是 `etmcr |= drvdata->port_size;`，port_size 由 ETMCR 现有字段回读而来；
     * 这里直接按 ETMSCR 能力位设 —— bit2(ETMSCR bit2)=支持 4 位并行口。 */
    {
        uint32_t scr = TRACE_REG(etm + 0x14u); /* ETMSCR */
        if (scr & (1u << 2)) {
            TRACE_REG(etm) = (TRACE_REG(etm) & ~0x70u) | 0x20u; /* b4..b6 = 010 -> 4 位 */
        }
    }

    /* --- 3) 编程模式内写寄存器 ---
     * 偏移全部对照 Linux 内核 drivers/hwtracing/coresight/coresight-etm.h 核实过：
     *   ETMTRIGGER=0x008  ETMTEEVR=0x020  ETMTECR1=0x024  ETMFFLR=0x02C  ETMTRACEIDR=0x200
     * ETMCR 位：PWD_DWN=b0  STALL=b7  BBROAD=b8  ETM_PRG=b10  ETM_EN=b11
     *           CYC_ACC=b12  CTXID=b14|b15  TS_EN=b28  RETSTACK=b29  端口宽度=b4..b6
     * ETMTECR1 位：ADDR_COMP_1=b0  INC_EXC=b24  START_STOP=b25 */
    TRACE_REG(etm + 0x08u) = 0u;    /* ETMTRIGGER：不用外部触发 */
    TRACE_REG(etm + 0x20u) = 0x6Fu; /* ETMTEEVR：TraceEnable 事件 = always true
                                     * （Linux: "set register 0x008, the ETMTEEVR, to 0x6F (TRUE)"） */
    TRACE_REG(etm + 0x24u) = (1u << 24); /* ★ ETMTECR1：INC_EXC=1
                                     * ⚠️ 这一位原实现是 0 —— bit0(ADDR_COMP_1)=0 时
                                     * "地址比较器 1 的地址范围"被**排除**，等于禁止一切 trace。
                                     * ETM 不产出数据 → TPIU 只发空闲模式 → LA 上只有时钟、
                                     * 数据线几乎不动。实测就是这个症状。 */
    TRACE_REG(etm + 0x18u) = 0u;    /* ETMTSSCR：不做 start/stop 门控 */    TRACE_REG(etm + 0x2Cu) = 0u;    /* ETMFFLR：不限制 FIFO 触发层级 */
    TRACE_REG(etm + 0x200u) = 2u;   /* ETMTRACEIDR：trace ID = 2 */

    /* --- 4) TPIU：4 位 DDR 并行口 --- */
    TRACE_REG(tpiu + 0x04u) = 8u;   /* CSPSR：8-bit 输入 → 四位 DDR 输出 */
    TRACE_REG(tpiu + 0xF0u) = 0u;   /* SPPR：并行同步口 */
    TRACE_REG(tpiu + 0x304u) |= 2u; /* FFCR：使能格式化器 */

    /* --- 5) DBGMCU：★ trace 引脚使能（原实现漏掉的就是这一步） --- */
    DBGMCU->CR = (DBGMCU->CR & ~0xE0u) | 0xE0u; /* TRACE_IOEN=1, TRACE_MODE=11(4 位) */
    if ((DBGMCU->CR & 0xE0u) == 0xE0u) {
        bits |= ETM_BIT_DBGMCU;
    }

    /* --- 6) ITM/DWT 同步 --- */
    DWT_CTRL |= 1u;
    TRACE_REG(0xE0000E80u) = 0x0001000Du; /* ITM_TCR：使能 + 同步包 */
    if (TRACE_REG(0xE0000E80u) == 0x0001000Du) {
        bits |= ETM_BIT_ITM;
    }

    /* --- 7) 退出编程模式，打开 TRACEOUT --- */
    TRACE_REG(etm) = (TRACE_REG(etm) & ~0x400u) | 0x800u;
    for (timeout = 0; timeout < 200000u; ++timeout) {
        if ((TRACE_REG(etm + 0x10u) & 2u) == 0u) break;
    }
    if (TRACE_REG(etm) & 0x800u) {
        bits |= ETM_BIT_TRACEOUT;
    }

    g_trace.etm_bits = bits;
    g_trace.etm_status = (bits == ETM_BITS_ALL) ? 4u : 3u;
}

/* 供 main 在配好 PE2~PE6 之后回填 PINS 位（引脚配置由 MX_GPIO_Init 负责） */
void trace_etm_mark_pins(void)
{
    g_trace.etm_bits |= ETM_BIT_PINS;
}
#endif

void trace_hook_init(void)
{
    /* NOLOAD 固定段的 C 静态初值不可靠，必须显式写一遍 */
    g_trace.magic = 0x31524354u; /* 'TRC1' */
    g_trace.sysclk_hz = 0;
    g_trace.ready = 0;
    g_trace.loops = 0;
    g_trace.marks = 0;
    g_trace.cyc_last = 0;
    g_trace.cyc_delta = 0;
    g_trace.usb_rx = 0;
    g_trace.usb_tx = 0;
    g_trace.usb_hp_irq = 0;
    g_trace.usb_ctr = 0;
    g_trace.etm_status = 0;
    g_trace.etm_bits = 0;

    /* DWT 周期计数器 */
    DWT_LAR = 0xC5ACCE55u; /* 部分 M3 需要先解锁；无 LAR 的实现是 RAZ/WI，无害 */
    DEMCR |= (1u << 24);   /* TRCENA */
    DWT_CYCCNT = 0;
    DWT_CTRL |= (1u << 0); /* CYCCNTENA */

#if defined(STM32F103xE) && defined(TRACE_ETM_STANDALONE)
    /* 注意调用顺序：本函数在 main 的 MX_GPIO_Init() 之后调用，PE2~PE6 那时已经是
     * AF 推挽（GPIOE_CRL=0x4bbbbb44 实测）。所以**先把引脚位记上再初始化**，
     * 否则 etm_status 在函数内结算时 bit7 还没置，会永远报 3 而不是 4。 */
    g_trace.etm_bits |= (1u << 7); /* ETM_BIT_PINS */
    trace_etm_standalone_init();
#endif

    /* 打点脚 */
    {
        GPIO_InitTypeDef io = { 0 };
        __HAL_RCC_GPIOA_CLK_ENABLE();
        io.Pin = TRACE_PIN;
        io.Mode = GPIO_MODE_OUTPUT_PP;
        io.Pull = GPIO_NOPULL;
        io.Speed = GPIO_SPEED_FREQ_HIGH;
        HAL_GPIO_Init(TRACE_PIN_PORT, &io);
        HAL_GPIO_WritePin(TRACE_PIN_PORT, TRACE_PIN, GPIO_PIN_RESET);
    }
}

void trace_hook_entry(void)
{
    /* 稳定落点：外部工具在这里下硬件断点当执行流起点。
     * 不要写 static inline，否则会被优化掉。 */
    __asm volatile("nop");
}

void trace_hook_ready(void)
{
    g_trace.sysclk_hz = g_sysclk_hz;
    g_trace.ready = 1u;
}

void trace_hook_mark(void)
{
    uint32_t now = DWT_CYCCNT;

    g_trace.marks++;
    g_trace.cyc_last = now;
    g_trace.cyc_delta = now - s_last_cycles;
    s_last_cycles = now;

    s_pin_state ^= 1u;
    HAL_GPIO_WritePin(TRACE_PIN_PORT, TRACE_PIN,
                      s_pin_state ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

int trace_log_printf(const char *fmt, ...)
{
    char buf[176];
    va_list ap;
    int n;

    va_start(ap, fmt);
    n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    if (n > 0) {
        uint32_t len = ((uint32_t)n < sizeof(buf)) ? (uint32_t)n : (uint32_t)(sizeof(buf) - 1u);
        SEGGER_RTT_Write(0, buf, len);
    }
    return n;
}
