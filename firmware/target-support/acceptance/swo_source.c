#include "fixture.h"
#include "stm32h743xx.h"

/* GPIO waveform source. TIM2_UP drives DMA1/DMAMUX1 into PB3's BSRR. */
#define MAX_BYTES 256u
#define PIN 3u
#define STREAM DMA1_Stream0
#define DMA_ERRORS (DMA_LISR_FEIF0 | DMA_LISR_DMEIF0 | DMA_LISR_TEIF0)
#define DMA_FLAGS (DMA_ERRORS | DMA_LISR_HTIF0 | DMA_LISR_TCIF0)

SHARED volatile uint32_t g_source_request, g_source_mode, g_source_ticks, g_source_repeats;
SHARED volatile uint32_t g_source_sent, g_source_status, g_source_symbol_hz;
SHARED uint8_t g_source_payload[MAX_BYTES];
SHARED static uint32_t waveform[MAX_BYTES * 24u + 32u];

static void emit(unsigned *count, bool level)
{
    waveform[(*count)++] = 1u << (PIN + (level ? 0u : 16u));
}

static void idle(unsigned *count, bool manchester)
{
    for (unsigned i = 0; i < 6; ++i) emit(count, !manchester);
}

static unsigned encode(unsigned bytes, bool manchester)
{
    unsigned count = 0;
    idle(&count, manchester);
    for (unsigned i = 0; i < bytes; ++i) {
        if (manchester && !(i & 7u)) {
            emit(&count, true);
            emit(&count, false);
        } else if (!manchester) {
            emit(&count, false);
        }
        for (unsigned bit = 0; bit < 8; ++bit) {
            bool value = (g_source_payload[i] >> bit) & 1u;
            emit(&count, value);
            if (manchester) emit(&count, !value);
        }
        if (!manchester) emit(&count, true);
        if (manchester && ((i & 7u) == 7 || i + 1u == bytes))
            idle(&count, true);
    }
    idle(&count, manchester);
    return count;
}

static unsigned send(unsigned count, unsigned bytes, unsigned ticks, unsigned repeats, bool manchester)
{
    GPIOB->BSRR = 1u << (PIN + (manchester ? 16u : 0u));
    TIM2->CR1 = 0;
    TIM2->DIER = 0;
    TIM2->PSC = 0;
    TIM2->ARR = ticks - 1u;
    TIM2->EGR = TIM_EGR_UG;
    TIM2->SR = 0;
    DMA1->LIFCR = DMA_FLAGS;
    DMAMUX1_Channel0->CCR = 22; /* TIM2_UP */
    STREAM->PAR = (uintptr_t)&GPIOB->BSRR;
    STREAM->M0AR = (uintptr_t)waveform;
    STREAM->NDTR = count;
    STREAM->FCR = DMA_SxFCR_DMDIS | DMA_SxFCR_FTH_0;
    STREAM->CR = DMA_SxCR_MINC | DMA_SxCR_DIR_0 | DMA_SxCR_MSIZE_1 | DMA_SxCR_PSIZE_1 |
                 DMA_SxCR_PL_1 | (repeats > 1 ? DMA_SxCR_CIRC : 0);
    publish();
    STREAM->CR |= DMA_SxCR_EN;
    TIM2->DIER = TIM_DIER_UDE;
    TIM2->CR1 = TIM_CR1_CEN;
    uint32_t deadline = target_tick() + g_cpu_hz;
    unsigned result = 2;
    while (repeats) {
        uint32_t flags = DMA1->LISR;
        if (flags & DMA_ERRORS) { result = 3; break; }
        if (flags & DMA_LISR_TCIF0) {
            DMA1->LIFCR = DMA_LIFCR_CTCIF0;
            g_source_sent += bytes;
            --repeats;
            deadline = target_tick() + g_cpu_hz;
        } else if ((int32_t)(target_tick() - deadline) >= 0) {
            result = 4;
            break;
        }
    }
    TIM2->CR1 = 0;
    TIM2->DIER = 0;
    STREAM->CR &= ~DMA_SxCR_EN;
    for (unsigned retry = 100000; STREAM->CR & DMA_SxCR_EN; ) {
        if (!--retry) { result = 5; break; }
    }
    GPIOB->BSRR = 1u << (PIN + (manchester ? 16u : 0u));
    return result;
}

int main(void)
{
    if (!target_clock_init()) for (;;) {}
    RCC->AHB4ENR |= RCC_AHB4ENR_GPIOBEN;
    RCC->AHB1ENR |= RCC_AHB1ENR_DMA1EN;
    RCC->APB1LENR |= RCC_APB1LENR_TIM2EN;
    (void)RCC->APB1LENR;
    GPIOB->BSRR = 1u << PIN;
    GPIOB->MODER = (GPIOB->MODER & ~(3u << (2u * PIN))) | (1u << (2u * PIN));
    GPIOB->OSPEEDR |= 3u << (2u * PIN);
    g_source_ticks = 16;
    g_source_repeats = 1;
    uint32_t pattern = 1;
    for (unsigned i = 0; i < MAX_BYTES; ++i) {
        pattern = pattern * 1664525u + 1013904223u;
        g_source_payload[i] = pattern >> 24;
    }
    publish();
    g_fixture_ready = 0x53574f53u;
    for (;;) {
        unsigned bytes = g_source_request;
        if (!bytes) continue;
        unsigned ticks = g_source_ticks, repeats = g_source_repeats, mode = g_source_mode;
        g_source_request = 0;
        if (bytes > MAX_BYTES || ticks < 16 || ticks > 65535 || !repeats ||
            repeats > UINT32_MAX / bytes || mode > 1) {
            g_source_status = 6;
            continue;
        }
        g_source_sent = 0;
        g_source_symbol_hz = g_hclk_hz / ticks;
        g_source_status = 1;
        unsigned result = send(encode(bytes, mode), bytes, ticks, repeats, mode);
        publish();
        g_source_status = result;
    }
}
