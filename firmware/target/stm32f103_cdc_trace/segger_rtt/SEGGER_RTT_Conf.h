/*
 * SEGGER RTT 配置 —— STM32F103（20KB RAM）专用
 *
 * F103CB 只有 20KB SRAM，不能用 H743 那份 12KB 上行缓冲的配置。
 * 这里取保守值：上行 512B、下行 16B，缓冲满就丢日志（绝不阻塞目标）。
 */
#ifndef SEGGER_RTT_CONF_H
#define SEGGER_RTT_CONF_H

#define BUFFER_SIZE_UP                  (512)   /* ch0 上行：够放启动日志 */
#define BUFFER_SIZE_DOWN                (16)    /* ch0 下行：不用输入 */
#define SEGGER_RTT_MAX_NUM_UP_BUFFERS   (1)
#define SEGGER_RTT_MAX_NUM_DOWN_BUFFERS (1)
#define SEGGER_RTT_MODE_DEFAULT         SEGGER_RTT_MODE_NO_BLOCK_SKIP
#define SEGGER_RTT_LOCK()
#define SEGGER_RTT_UNLOCK()

#endif
