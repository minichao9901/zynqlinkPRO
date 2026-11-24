/*
 * CherryUSB 配置 —— STM32F103 CDC ACM
 *
 * 基线：参照工程 cherry_drag_n_drop_bootloader_fat16\Inc\usb_config.h（v1.5.2）
 *       —— 那份能在这块板子上跑通枚举，这里只做两处必要改动：
 *         1) CONFIG_USB_PRINTF 改到 SEGGER RTT（不占用 USART1，也不需要 SWO 引脚）
 *         2) 去掉用不到的 MSC / RNDIS / MTP / ECM / Host 相关配置
 *       device 侧真正必须的宏一个都没动。
 */
#ifndef CHERRYUSB_CONFIG_H
#define CHERRYUSB_CONFIG_H

/* ================ USB common Configuration ================ */

#include <stdio.h>
#include "trace_hooks.h"

/* 调试输出走 SEGGER RTT（trace_log_printf 在 src/trace_hooks.c） */
#define CONFIG_USB_PRINTF(...) trace_log_printf(__VA_ARGS__)

/* fsdev 不允许开到 USB_DBG_LOG（驱动里有 #error 自检） */
#ifndef CONFIG_USB_DBG_LEVEL
#define CONFIG_USB_DBG_LEVEL USB_DBG_INFO
#endif

/* 不带颜色：RTT 里看 ANSI 转义码没意义 */
// #define CONFIG_USB_PRINTF_COLOR_ENABLE

/* F1 无 D-Cache、USB 无 DMA：4 字节对齐即可 */
#define CONFIG_USB_ALIGN_SIZE 4

/* 不要求无缓存段，直接放普通 .bss（省掉改链接脚本） */
#define USB_NOCACHE_RAM_SECTION
#ifndef USB_MEM_ALIGNX
#define USB_MEM_ALIGNX __attribute__((aligned(CONFIG_USB_ALIGN_SIZE)))
#endif

/* 用 CherryUSB 自带的 usb_memcpy（避免 newlib memcpy 非 4 字节对齐问题） */
// #define CONFIG_USB_MEMCPY_DISABLE

/* ================= USB Device Stack Configuration ================ */

/* EP0 收发缓冲（与参照工程一致） */
#ifndef CONFIG_USBDEV_REQUEST_BUFFER_LEN
#define CONFIG_USBDEV_REQUEST_BUFFER_LEN 512
#endif

/* 高级描述符接口（回调式）—— cdc_acm_template.c 用的就是这套 */
#define CONFIG_USBDEV_ADVANCE_DESC

/* 裸机，无 RTOS：EP0 setup 留在中断里处理 */
// #define CONFIG_USBDEV_EP0_THREAD

#define CONFIG_USBDEV_MAX_BUS 1

/* ================ USB Device Port Configuration ================*/

/* ---------------- FSDEV Configuration ---------------- */
/* STM32F1 的 PMA 必须按 16 位访问 → PMA_ACCESS = 2
 * （依据：stm32f1xx_ll_usb.h 里 `#define PMA_ACCESS 2U`；CherryUSB 的 glue 有编译期自检） */
#define CONFIG_USBDEV_FSDEV_PMA_ACCESS 2

/* F103 的 USB 专用 RAM 是 512 字节 */
#define CONFIG_USB_FSDEV_RAM_SIZE 512

#endif /* CHERRYUSB_CONFIG_H */
