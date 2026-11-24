#include "fixture.h"
#include "stm32f103xe.h"

#define BUFFER_BYTES 4096
#define DMA_RX (DMA1_Channel2)
#define DMA_TX (DMA1_Channel3)

SHARED volatile uint32_t g_spi_arm, g_spi_status, g_spi_role, g_spi_mode, g_spi_div;
SHARED volatile uint32_t g_spi_length, g_spi_delay_ms, g_spi_timeout_ms, g_spi_wire_hz;
SHARED volatile uint32_t g_spi_tx_seed, g_spi_rx_hash, g_spi_rx_bytes;
SHARED volatile uint32_t g_spi_stream_ms;
SHARED uint8_t g_spi_tx[BUFFER_BYTES], g_spi_rx[BUFFER_BYTES];

static void configure_pins(bool master)
{
    /* PA4/5/6/7 = NSS/SCK/MISO/MOSI. Master uses software NSS. */
    GPIOA->BSRR = 1u << 4;
    GPIOA->CRL = (GPIOA->CRL & 0xffffu) | (master ? 0xb4b30000u : 0x4b440000u);
}

static uint32_t transaction(uint32_t length, bool master, uint32_t mode, uint32_t divider,
                            uint32_t delay, uint32_t timeout, uint32_t seed, uint32_t stream_ms)
{
    uint32_t pattern = seed;
    for (uint32_t i = 0; i < length; ++i) {
        pattern = pattern * 1664525u + 1013904223u;
        g_spi_tx[i] = pattern >> 24;
    }
    configure_pins(master);
    SPI1->CR1 = mode | (divider << 3) |
                (master ? SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI : 0);
    SPI1->CR2 = 0;
    DMA1->IFCR = DMA_IFCR_CGIF2 | DMA_IFCR_CGIF3;
    DMA_RX->CNDTR = length;
    DMA_TX->CNDTR = length;
    DMA_RX->CPAR = DMA_TX->CPAR = (uintptr_t)&SPI1->DR;
    DMA_RX->CMAR = (uintptr_t)g_spi_rx;
    DMA_TX->CMAR = (uintptr_t)g_spi_tx;
    uint32_t circular = stream_ms ? DMA_CCR_CIRC : 0;
    DMA_RX->CCR = DMA_CCR_MINC | DMA_CCR_PL_1 | DMA_CCR_EN | circular;
    SPI1->CR2 = SPI_CR2_RXDMAEN;
    SPI1->CR1 |= SPI_CR1_SPE;
    uint32_t deadline = target_tick() + delay;
    while ((int32_t)(target_tick() - deadline) < 0) {}
    if (master) GPIOA->BSRR = 1u << 20;
    DMA_TX->CCR = DMA_CCR_MINC | DMA_CCR_DIR | DMA_CCR_PL_0 | DMA_CCR_EN | circular;
    SPI1->CR2 |= SPI_CR2_TXDMAEN;

    uint32_t result = 0;
    uint32_t previous = target_tick(), total = 0;
    uint64_t remaining = (uint64_t)stream_ms * (g_cpu_hz / 1000);
    deadline = previous + timeout;
    while (stream_ms ? remaining != 0 : (DMA_RX->CNDTR || DMA_TX->CNDTR || (SPI1->SR & SPI_SR_BSY))) {
        if (DMA1->ISR & (DMA_ISR_TEIF2 | DMA_ISR_TEIF3)) { result = 3; break; }
        uint32_t now = target_tick();
        if (stream_ms) {
            if (DMA1->ISR & DMA_ISR_TCIF2) {
                DMA1->IFCR = DMA_IFCR_CTCIF2;
                total += length;
            }
            uint32_t elapsed = now - previous;
            remaining = elapsed >= remaining ? 0 : remaining - elapsed;
            previous = now;
        } else if ((int32_t)(now - deadline) >= 0) {
            result = 4;
            break;
        }
    }
    if (master && stream_ms) {
        SPI1->CR2 &= ~SPI_CR2_TXDMAEN;
        deadline = target_tick() + g_cpu_hz / 100;
        while (SPI1->SR & (SPI_SR_BSY | SPI_SR_RXNE)) {
            if ((int32_t)(target_tick() - deadline) >= 0) { result = 4; break; }
        }
    }
    if (master) GPIOA->BSRR = 1u << 4;
    if (stream_ms && (DMA1->ISR & DMA_ISR_TCIF2)) total += length;
    uint32_t tail = length - DMA_RX->CNDTR;
    SPI1->CR2 = 0;
    DMA_RX->CCR = DMA_TX->CCR = 0;
    g_spi_rx_bytes = total + tail;
    if ((SPI1->SR & SPI_SR_OVR) && !result) result = 5;
    SPI1->CR1 = 0;
    (void)SPI1->DR;
    (void)SPI1->SR;
    GPIOA->CRL = (GPIOA->CRL & 0xffffu) | 0x44440000u;
    uint32_t hash = 2166136261u;
    for (uint32_t i = 0; i < (total ? length : tail); ++i)
        hash = (hash ^ g_spi_rx[i]) * 16777619u;
    g_spi_rx_hash = hash;
    return result;
}

int main(void)
{
    if (!target_clock_init()) for (;;) {}
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_SPI1EN;
    RCC->AHBENR |= RCC_AHBENR_DMA1EN;
    (void)RCC->AHBENR;
    GPIOA->CRL = (GPIOA->CRL & 0xffffu) | 0x44440000u;
    g_spi_div = 4;
    g_spi_timeout_ms = 2000;
    g_spi_delay_ms = 1000;
    g_spi_tx_seed = 1;
    publish();
    g_fixture_ready = 0x53504931u;
    for (;;) {
        if (!g_spi_arm) continue;
        g_spi_arm = 0;
        const uint32_t length = g_spi_length, role = g_spi_role, mode = g_spi_mode;
        const uint32_t divider = g_spi_div, delay = g_spi_delay_ms, timeout = g_spi_timeout_ms;
        const uint32_t stream_ms = g_spi_stream_ms;
        if (!length || length > BUFFER_BYTES || role > 1 || mode > 3 ||
            divider > 7 || delay > 5000 || !timeout || timeout > 10000 ||
            stream_ms > 120000 || (stream_ms && (!role || length < 256))) {
            g_spi_status = 2;
            continue;
        }
        g_spi_rx_bytes = 0;
        g_spi_wire_hz = role ? ((g_hclk_hz / 2) >> (divider + 1)) : 0;
        g_spi_status = 1;
        uint32_t result = transaction(length, role, mode, divider,
                                      (g_cpu_hz / 1000) * (role ? delay : 0),
                                      (g_cpu_hz / 1000) * timeout, g_spi_tx_seed, stream_ms);
        publish();
        g_spi_status = result ? result : 6;
    }
}
