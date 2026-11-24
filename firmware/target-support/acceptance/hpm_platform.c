#include "fixture.h"
#include "board.h"
#include "hpm_clock_drv.h"
#include "hpm_mchtmr_drv.h"
#include "hpm_uart_drv.h"

SHARED volatile uint32_t g_cpu_hz, g_hclk_hz, g_clock_error, g_fixture_ready, g_mchtmr_hz;

uint32_t target_clock_init(void)
{
    board_init();
    g_cpu_hz = clock_get_frequency(clock_cpu0);
    g_mchtmr_hz = clock_get_frequency(clock_mchtmr0);
    if (g_cpu_hz != 600000000 || !g_mchtmr_hz) {
        g_clock_error = 1;
        return 0;
    }
    return g_cpu_hz;
}

uint32_t target_tick(void) { return (uint32_t)mchtmr_get_count(HPM_MCHTMR); }
uint32_t target_tick_hz(void) { return g_mchtmr_hz; }

bool uart_configure(uint32_t baud)
{
    uart_config_t config;
    UART_Type *port = BOARD_APP_UART_BASE;
    board_init_uart(port);
    uart_default_config(port, &config);
    config.src_freq_in_hz = board_init_uart_clock(port);
    if (!baud || baud > config.src_freq_in_hz / 8u) return false;
    config.baudrate = baud;
    return uart_init(port, &config) == status_success;
}

bool uart_receive(uint8_t *byte, uint32_t *errors)
{
    uint32_t status = uart_get_status(BOARD_APP_UART_BASE);
    *errors = status & (UART_LSR_OE_MASK | UART_LSR_PE_MASK | UART_LSR_FE_MASK |
                       UART_LSR_ERRF_MASK | UART_LSR_LBREAK_MASK);
    if (!(status & UART_LSR_DR_MASK)) return false;
    *byte = uart_read_byte(BOARD_APP_UART_BASE);
    return true;
}

bool uart_send(uint8_t byte)
{
    UART_Type *port = BOARD_APP_UART_BASE;
    if (!(uart_get_status(port) & UART_LSR_THRE_MASK)) return false;
    port->THR = byte;
    return true;
}
