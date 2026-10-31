/*
 * STM32F103（CB/R8/ZE）+ CherryUSB CDC ACM 例程 + etm-trace 钩子
 * ============================================================================
 * 目录：E:\web-etm-trace\firmware\stm32f103_cdc_trace
 *
 * 基线说明（本工程怎么来的）：
 *   以你提供的参考工程 cherry_drag_n_drop_bootloader_fat16（MSC 拖拽 IAP，
 *   已在同一块板上验证可枚举）为基底，**只做三处改动**：
 *     1) USB 类：class/msc → class/cdc（用 CherryUSB demo/cdc_acm_template.c 改写）
 *     2) 时钟/GPIO/UART 初始化：直接沿用参考工程 main.c 的 SystemClock_Config / MX_GPIO_Init
 *        （ZE 默认 HSE 8MHz × PLL6 = 48MHz；CB 及显式对照档 PLL9 = 72MHz，USB 均为 48MHz）
 *     3) 增加 etm-trace 钩子（SEGGER RTT 日志 + DWT 打点），删掉 MSC/flash_fat16/DFU 相关文件
 *   USB 底层（usb_dc_fsdev.c / usb_fsdev_reg.h / usb_glue_st.c / usb_config.h）保持原样，
 *   唯一额外的构建前准备是 tools/prep.ps1（解开 ST 启动文件对 USB 中断的弱别名锁定，
 *   原因见该脚本注释与 README）。
 *
 * CDC 命令（串口工具/脚本，DTR 必须拉起来）：
 *   PING | INFO | MARK | ECHO on|off | ECHO <text>
 *   默认"收到什么回什么"。
 *
 * 构建：pwsh -NoProfile -File .\build.ps1            （默认 -Chip cb，在线板）
 *       pwsh -NoProfile -File .\build.ps1 -Chip ze  （F103ZE 目标板，带 ETM）
 */
#include "main.h"
#include "usbd_core.h"
#include "usbd_cdc_acm.h"
#include "trace_hooks.h"
#include "cdc_console.h"
#include "SEGGER_RTT.h"
#include "trace_workload.h"

#if (defined(TRACE_CPU_24MHZ) + defined(TRACE_CPU_48MHZ) + defined(TRACE_CPU_72MHZ)) > 1
#error "Choose only one CPU clock profile"
#endif
#if defined(STM32F103xE) && !defined(TRACE_CPU_72MHZ) && !defined(TRACE_CPU_48MHZ) && !defined(TRACE_CPU_24MHZ)
#define TRACE_CPU_48MHZ
#endif

#include <string.h>
#include <stdio.h>

UART_HandleTypeDef huart1;

/* 时钟实测值，给 trace_hooks.c 用 */
uint32_t g_sysclk_hz = 0;
uint32_t g_clock_err = 0;

/* ======================= CherryUSB CDC ACM 描述符 =======================
 * 端点号与 demo/cdc_acm_template.c 一致：INT=0x83 / OUT=0x02 / IN=0x81 */
#define CDC_IN_EP  0x81
#define CDC_OUT_EP 0x02
#define CDC_INT_EP 0x83

#define USBD_VID           0xF055
#define USBD_PID           0x1031
#define USBD_MAX_POWER     100
#define USBD_LANGID_STRING 1033

#define USB_CONFIG_SIZE (9 + CDC_ACM_DESCRIPTOR_LEN)

/* F103 只有全速 USB，包长固定 64 */
#define CDC_MAX_MPS 64

/* 模板里是 2048；F103CB 只有 20KB RAM，缩到 512（逻辑完全一样） */
#define CDC_BUF_SIZE 512

static const uint8_t device_descriptor[] = {
    USB_DEVICE_DESCRIPTOR_INIT(USB_2_0, 0xEF, 0x02, 0x01, USBD_VID, USBD_PID, 0x0100, 0x01)
};

static const uint8_t config_descriptor[] = {
    USB_CONFIG_DESCRIPTOR_INIT(USB_CONFIG_SIZE, 0x02, 0x01, USB_CONFIG_BUS_POWERED, USBD_MAX_POWER),
    CDC_ACM_DESCRIPTOR_INIT(0x00, CDC_INT_EP, CDC_OUT_EP, CDC_IN_EP, CDC_MAX_MPS, 0x02)
};

static const uint8_t device_quality_descriptor[] = {
    /* device qualifier（FS 设备也要给，Windows 会问） */
    0x0a, USB_DESCRIPTOR_TYPE_DEVICE_QUALIFIER,
    0x00, 0x02, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00,
};

static const char *string_descriptors[] = {
    (const char[]){ 0x09, 0x04 }, /* Langid = 1033 */
    "web-etm-trace",              /* Manufacturer */
    "STM32F103 CDC ACM (CherryUSB)", /* Product */
    "F103CDC0001",                /* Serial */
};

static const uint8_t *device_descriptor_callback(uint8_t speed)
{
    (void)speed; return device_descriptor;
}
static const uint8_t *config_descriptor_callback(uint8_t speed)
{
    (void)speed; return config_descriptor;
}
static const uint8_t *device_quality_descriptor_callback(uint8_t speed)
{
    (void)speed; return device_quality_descriptor;
}
static const char *string_descriptor_callback(uint8_t speed, uint8_t index)
{
    (void)speed;
    if (index >= (sizeof(string_descriptors) / sizeof(char *))) return NULL;
    return string_descriptors[index];
}

static const struct usb_descriptor cdc_descriptor = {
    .device_descriptor_callback = device_descriptor_callback,
    .config_descriptor_callback = config_descriptor_callback,
    .device_quality_descriptor_callback = device_quality_descriptor_callback,
    .string_descriptor_callback = string_descriptor_callback
};

/* ======================= 端点缓冲 =======================
 * 缓冲大小与 H7B0 的 CDC_RX_SIZE/CDC_TX_SIZE 不同：F103CB 只有 20KB RAM。 */
static uint8_t read_buffer[CDC_BUF_SIZE];
static uint8_t write_buffer[CDC_BUF_SIZE];

static volatile uint32_t rx_len;
static uint32_t rx_processed;
static volatile uint8_t rx_pending;
static uint8_t rx_armed;
static volatile uint32_t rx_total;
static volatile uint32_t tx_total;
static volatile uint8_t ep_tx_busy_flag;
static volatile uint8_t dtr_enable;
static volatile uint8_t usb_configured;
static uint8_t banner_sent;

static const char banner[] =
    "\r\n=== STM32F103 CherryUSB CDC ACM (etm-trace target) ===\r\n"
    "commands: PING | INFO | MARK | ECHO on|off | ECHO <text>\r\n";

/* ======================= USB 事件回调 =======================
 * 回调只更新标志；队列与接收缓冲由主循环在临界区里统一处理（见 cdc_poll）。 */
static void cdc_session_reset(void)
{
    usb_configured = 0;
    dtr_enable = 0;
    rx_pending = rx_armed = 0;
    rx_len = rx_processed = 0;
    ep_tx_busy_flag = banner_sent = 0;
    cdc_console_reset();
}

static void usbd_event_handler(uint8_t busid, uint8_t event)
{
    (void)busid;
    switch (event) {
        case USBD_EVENT_RESET:
            cdc_session_reset();
            USB_LOG_RAW("[usb] reset\r\n");
            break;
        case USBD_EVENT_CONNECTED:
            USB_LOG_RAW("[usb] connected\r\n");
            break;
        case USBD_EVENT_DISCONNECTED:
            cdc_session_reset();
            USB_LOG_RAW("[usb] disconnected\r\n");
            break;
        case USBD_EVENT_RESUME:
        case USBD_EVENT_SUSPEND:
            break;
        case USBD_EVENT_CONFIGURED:
            cdc_session_reset();
            usb_configured = 1;
            USB_LOG_RAW("[usb] configured\r\n");
            break;
        case USBD_EVENT_SET_REMOTE_WAKEUP:
        case USBD_EVENT_CLR_REMOTE_WAKEUP:
            break;
        default:
            break;
    }
}

void usbd_cdc_acm_bulk_out(uint8_t busid, uint8_t ep, uint32_t nbytes)
{
    (void)busid;
    (void)ep;
    rx_armed = 0;
    rx_len = nbytes;
    rx_processed = 0;
    rx_pending = 1;
    rx_total += nbytes;
    g_trace.usb_rx = rx_total;
    /* 主循环处理完这包才重新接收；TX 满时通过 OUT NAK 施加背压。 */
}

void usbd_cdc_acm_bulk_in(uint8_t busid, uint8_t ep, uint32_t nbytes)
{
    tx_total += nbytes;
    g_trace.usb_tx = tx_total;

    uint16_t mps = usbd_get_ep_mps(busid, ep);
    if (usb_configured && mps && nbytes && (nbytes % mps) == 0) {
        /* 整包后补 ZLP；ZLP 完成前保持忙标志。 */
        if (usbd_ep_start_write(busid, CDC_IN_EP, NULL, 0) != 0) {
            ep_tx_busy_flag = 0;
        }
    } else {
        ep_tx_busy_flag = 0;
    }
}

static struct usbd_endpoint cdc_out_ep = { .ep_addr = CDC_OUT_EP, .ep_cb = usbd_cdc_acm_bulk_out };
static struct usbd_endpoint cdc_in_ep = { .ep_addr = CDC_IN_EP, .ep_cb = usbd_cdc_acm_bulk_in };
static struct usbd_interface intf0;
static struct usbd_interface intf1;

/* CDC 类请求回调（模板里是 __WEAK，这里给真实实现） */
void usbd_cdc_acm_set_dtr(uint8_t busid, uint8_t intf, bool dtr)
{
    (void)busid;
    (void)intf;
    dtr_enable = dtr ? 1 : 0;
    if (!dtr) {
        /* 关闭串口：清命令行和待发队列，再次打开时重新发欢迎信息。 */
        cdc_console_reset();
        rx_processed = rx_len;
        banner_sent = 0;
    }
}

void usbd_cdc_acm_set_rts(uint8_t busid, uint8_t intf, bool rts)
{
    (void)busid;
    (void)intf;
    (void)rts;
}

static int cdc_acm_init(uint8_t busid, uintptr_t reg_base)
{
    usbd_desc_register(busid, &cdc_descriptor);
    usbd_add_interface(busid, usbd_cdc_acm_init_intf(busid, &intf0));
    usbd_add_interface(busid, usbd_cdc_acm_init_intf(busid, &intf1));
    usbd_add_endpoint(busid, &cdc_out_ep);
    usbd_add_endpoint(busid, &cdc_in_ep);

    cdc_session_reset();
    /* 内部会调 usb_dc_init() → usb_dc_low_level_init()，
     * 后者在 usb_glue_st.c 里走 HAL_PCD_MspInit 开时钟与中断。 */
    return usbd_initialize(busid, reg_base, usbd_event_handler);
}

/* ======================= 主循环收发 =======================
 * 调用前必须关中断（见 cdc_poll），与 USB 回调串行化对队列和缓冲的所有权。 */
static void cdc_tx_poll(void)
{
    if (!usb_configured || !dtr_enable || ep_tx_busy_flag) {
        return;
    }
    uint32_t n = (uint32_t)cdc_console_peek(write_buffer, sizeof(write_buffer));
    if (n) {
        ep_tx_busy_flag = 1;
        if (usbd_ep_start_write(0, CDC_IN_EP, write_buffer, n) == 0) {
            cdc_console_consume(n);
        } else {
            ep_tx_busy_flag = 0; /* 保留队列数据，下次重试 */
        }
    }
}

static void cdc_poll(void)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();

    /* 每次只解析一包 64 字节，主循环里不做等待或 RTT 日志。 */
    if (usb_configured && !usb_device_is_configured(0)) {
        cdc_session_reset(); /* SET_CONFIGURATION(0) 不会触发回调 */
    }
    if (usb_configured) {
        cdc_tx_poll();
        if (dtr_enable && !banner_sent &&
            cdc_console_write((const uint8_t *)banner, sizeof(banner) - 1u)) {
            banner_sent = 1;
        }
        if (rx_pending) {
            if (dtr_enable) {
                rx_processed += (uint32_t)cdc_console_feed(
                    read_buffer + rx_processed, rx_len - rx_processed);
            } else {
                rx_processed = rx_len;
            }
            if (rx_processed == rx_len) {
                rx_pending = 0;
            }
        }
        if (!rx_pending && !rx_armed) {
            if (usbd_ep_start_read(0, CDC_OUT_EP, read_buffer, CDC_MAX_MPS) == 0) {
                rx_armed = 1;
            }
        }
        cdc_tx_poll();
    }
    __set_PRIMASK(primask);
}

/* ======================= CDC 命令行（协议由 cdc_console.c 负责）=======================
 * 板级回调：INFO 字段与 H7B0 不同（F103 没有 TRACECLK）。
 * usbhp/ctr 用于排查枚举；RESET/ERR/SUSP 走 LP 向量，本工程不计数（见 trace_hooks.h）。 */
size_t cdc_console_info(char *out, size_t capacity)
{
    int n = snprintf(out, capacity,
                     "chip=STM32F103 sysclk=%luHz clk_err=%lu loops=%lu marks=%lu rx=%lu tx=%lu "
                     "usbhp=%lu ctr=%lu\r\n",
                     (unsigned long)g_sysclk_hz, (unsigned long)g_clock_err,
                     (unsigned long)g_trace.loops, (unsigned long)g_trace.marks,
                     (unsigned long)rx_total, (unsigned long)tx_total,
                     (unsigned long)g_trace.usb_hp_irq, (unsigned long)g_trace.usb_ctr);
    return n > 0 ? (size_t)n : 0u;
}

void cdc_console_mark(void)
{
    trace_hook_mark();
}

/* ======================= 时钟 / 外设初始化（沿用参考工程） ======================= */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = { 0 };
    RCC_ClkInitTypeDef RCC_ClkInitStruct = { 0 };
    RCC_PeriphCLKInitTypeDef PeriphClkInit = { 0 };

    /* F103ZE defaults to PLL6: CPU/HCLK 48 MHz, TRACECLK 24 MHz, USB 48 MHz.
     * PLL9 remains available as an explicit 72/36 MHz comparison build. */
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
#if defined(TRACE_CPU_48MHZ) || defined(TRACE_CPU_24MHZ)
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL6;
#else
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
#endif
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) {
        g_clock_err |= 1u;
    }

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
#ifdef TRACE_CPU_24MHZ
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV2; /* PLL48 retains USB48, CPU24/TRACECLK12. */
#else
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
#endif
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
#ifdef TRACE_CPU_24MHZ
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK) {
#elif defined(TRACE_CPU_48MHZ)
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_1) != HAL_OK) {
#else
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
#endif
        g_clock_err |= 2u;
    }

    /* USB 时钟固定为 48 MHz：72 MHz 档 PLL /1.5，48 MHz 档 PLL /1。 */
    PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_USB;
#if defined(TRACE_CPU_48MHZ) || defined(TRACE_CPU_24MHZ)
    PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL;
#else
    PeriphClkInit.UsbClockSelection = RCC_USBCLKSOURCE_PLL_DIV1_5;
#endif
    if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK) {
        g_clock_err |= 4u;
    }

    g_sysclk_hz = HAL_RCC_GetHCLKFreq();
}

static void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = { 0 };

    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();

#if defined(STM32F103xE)
    /* Parallel ETM trace output: PE2=TRACECLK, PE3..PE6=TRACED0..3.
     * These pins reset as floating inputs.  DBGMCU_CR selects the trace
     * function later, but the GPIO output stages must be configured here.
     * Keep this independent of the host's ETM/TPIU enable sequence. */
    __HAL_RCC_GPIOE_CLK_ENABLE();
    GPIO_InitStruct.Pin = GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_4 |
                          GPIO_PIN_5 | GPIO_PIN_6;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH; /* F1: 50 MHz output mode */
    HAL_GPIO_Init(GPIOE, &GPIO_InitStruct);
#endif

    /* PA0：保留参照工程的输入脚（不驱动，避免与板级跳线冲突）。
     * PA1：trace 打点脚，由 trace_hooks.c 初始化为推挽输出。 */
    GPIO_InitStruct.Pin = GPIO_PIN_0;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLDOWN;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    /* PB2：参照工程的状态输出脚，保留以免板级行为变化。 */
    GPIO_InitStruct.Pin = GPIO_PIN_2;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}

static void MX_USART1_UART_Init(void)
{
    huart1.Instance = USART1;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    if (HAL_UART_Init(&huart1) != HAL_OK) {
        g_clock_err |= 8u;
    }
}

/* ======================= main ======================= */
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    SystemCoreClockUpdate();
    MX_GPIO_Init();
    MX_USART1_UART_Init();

    SEGGER_RTT_Init();
    trace_log_printf("\r\n=== STM32F103 CDC ACM (CherryUSB) ===\r\n");
    trace_log_printf("SYSCLK=%lu Hz, HCLK=%lu Hz, clock_err=%lu\r\n",
                     (unsigned long)HAL_RCC_GetSysClockFreq(),
                     (unsigned long)HAL_RCC_GetHCLKFreq(),
                     (unsigned long)g_clock_err);

    trace_hook_init();
    trace_hook_entry();

    (void)cdc_acm_init(0, (uintptr_t)USB_BASE);
    trace_log_printf("usb initialized (USB_BASE=0x%08lx)\r\n", (unsigned long)USB_BASE);

    trace_hook_ready();

    for (;;) {
        g_trace.loops++;

        /* 每轮只处理一包；RTT 日志与 USB 回调互不阻塞。 */
        cdc_poll();

#ifdef TRACE_PATH_WORKLOAD
        trace_workload_round(g_trace.loops);
#endif

        if ((g_trace.loops & 0xFFFFFu) == 0u) {
            trace_hook_mark();
        }
    }
}
