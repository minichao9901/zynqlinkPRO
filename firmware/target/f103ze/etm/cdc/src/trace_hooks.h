/*
 * etm-trace 钩子（STM32F103 / Cortex-M3）
 *
 * 与 stm32h7b0_spi_trace 同一约定：**固件不配置、不开启 trace 外设**，
 * 只给外部 SWD 工具提供：
 *   trace_hook_entry()   稳定落点（下硬件断点当执行流起点）
 *   trace_hook_ready()   置 g_trace.ready = 1（"可以开始采了"）
 *   trace_hook_mark()    周期性打点（DWT 周期 + 翻转 PA1 给逻辑分析仪）
 *   trace_hook_cycles()  读 DWT_CYCCNT
 *
 * ⚠️ F103 的 trace 能力按型号分档（详见 README 第 7 节）：
 *   · F103CB/RB/C8（64–128K，当前在线板）：**没有 ETM**，只有 ITM/SWO + DWT。
 *     指令流跟踪做不了；能做的是 DWT 周期/事件、ITM printf、SWO 打点、PC 采样。
 *   · F103ZE/xE（256–512K，目标板）：**有 ETMv3**（DS5792 Features 明写
 *     "Cortex-M3 Embedded Trace Macrocell"），换板后用 build.ps1 -Chip ze 重编即可，
 *     固件侧不用改 —— trace 寄存器由外部工具配。
 *
 * RTT 说明：trace_log_printf 走 SEGGER RTT，用普通 RAM 环形缓冲经 AHB-AP 读写，
 * **不需要 SWO 引脚**（要 SWO 的是 ITM/printf 重定向）。
 */
#ifndef __TRACE_HOOKS_H
#define __TRACE_HOOKS_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t magic;      /* 'T','R','C','1' */
    uint32_t sysclk_hz;  /* 实测 SYSCLK */
    uint32_t ready;      /* trace_hook_ready() 置 1 */
    uint32_t loops;      /* 主循环轮数 */
    uint32_t marks;      /* 打点次数 */
    uint32_t cyc_last;   /* 最近一次打点的 DWT 周期 */
    uint32_t cyc_delta;  /* 与上次打点的周期差 */
    uint32_t usb_rx;     /* CDC 收到字节数 */
    uint32_t usb_tx;     /* CDC 发出字节数 */
    /* USB 中断计数（只包含 HP 向量能观测到的事件）。
     * RESET/ERR/SUSP 走 LP 向量，由 CherryUSB glue 处理，这里不计数，避免 INFO 输出永远为 0 的字段误导排查。 */
    uint32_t usb_hp_irq; /* USB HP 向量进入次数 */
    uint32_t usb_ctr;    /* HP 向量内观测到的 CTR（传输完成）次数 */
    uint32_t etm_status; /* ZE 独立 ETM 模式：0=未启用，1=配置中，4=运行，2/3=失败 */
    /* 独立 ETM 的分步结果位图（etm_status==4 之后看这个判断哪一步没成）：
     *   bit0 TRCENA 已置   bit1 ETM 已解锁   bit2 TPIU 已解锁
     *   bit3 进编程模式成功 bit4 TRACEOUT 已使能
     *   bit5 DBGMCU.TRACE_IOEN/TRACE_MODE 已写   bit6 ITM_TCR 已写
     *   bit7 PE2~PE6 已配复用推挽
     * 0x1FF 表示全部完成。 */
    uint32_t etm_bits;
} trace_diag_t;

extern volatile trace_diag_t g_trace;

void trace_hook_init(void);
void trace_hook_entry(void);
void trace_hook_ready(void);
void trace_hook_mark(void);

static inline uint32_t trace_hook_cycles(void)
{
    return *(volatile uint32_t *)0xE0001004u; /* DWT_CYCCNT */
}

/* RTT 日志（同时作为 CherryUSB 的 CONFIG_USB_PRINTF） */
int trace_log_printf(const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* __TRACE_HOOKS_H */
