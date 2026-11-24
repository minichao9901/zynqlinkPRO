#include "fixture.h"

bool uart_configure(uint32_t baud);
bool uart_receive(uint8_t *byte, uint32_t *errors);
bool uart_send(uint8_t byte);

SHARED volatile uint32_t g_uart_baud_request, g_uart_baud, g_uart_config_errors;
SHARED volatile uint32_t g_uart_mode, g_uart_rx, g_uart_tx, g_uart_rx_errors;
SHARED volatile uint32_t g_uart_rx_hash, g_uart_tx_sequence;

int main(void)
{
    if (!target_clock_init()) for (;;) {}
    uint32_t tried = 115200;
    if (!uart_configure(tried)) for (;;) {}
    g_uart_baud = tried;
    g_uart_baud_request = tried;
    g_uart_rx_hash = 2166136261u;
    publish();
    g_fixture_ready = 0x55415254u;
    bool pending = false;
    uint8_t received = 0;
    for (;;) {
        uint32_t requested = g_uart_baud_request;
        if (requested != tried && g_uart_mode == 0 && !pending) {
            tried = requested;
            if (uart_configure(requested))
                g_uart_baud = requested;
            else
                ++g_uart_config_errors;
        }
        uint32_t errors = 0;
        if (!pending && uart_receive(&received, &errors)) {
            ++g_uart_rx;
            g_uart_rx_hash = (g_uart_rx_hash ^ received) * 16777619u;
            pending = g_uart_mode == 0;
        }
        if (errors) ++g_uart_rx_errors;
        if (pending) {
            if (uart_send(received ^ 0xa5u)) {
                pending = false;
                ++g_uart_tx;
            }
        } else if (g_uart_mode & 1u) {
            uint32_t byte = g_uart_tx_sequence;
            uint8_t value = (uint8_t)((byte >> 2) >> ((byte & 3u) * 8u));
            if (uart_send(value)) {
                ++g_uart_tx_sequence;
                ++g_uart_tx;
            }
        }
    }
}
