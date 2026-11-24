#include "stm32h7xx_hal.h"
#include "stm32h7xx_hal_dma.h"
#include "spi_fixture.h"
#include <inttypes.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { MAX_BYTES = 32768, STREAM_BYTES = 16384, MAX_MS = 120000 };
enum { NSS = 1u, SCK = 2u, MISO = 4u, MOSI = 8u, SPI_PINS = 15u };
enum { RX_SHIFT = 0, TX_SHIFT = 6, DMA_ALL = 0x3du, DMA_ERRORS = 0x0du, DMA_TC = 0x20u };
#define SPI_ERRORS (SPI_SR_OVR | SPI_SR_UDR | SPI_SR_MODF | SPI_SR_TIFRE | SPI_SR_CRCE)
#define SPI_CLEAR (SPI_IFCR_EOTC | SPI_IFCR_TXTFC | SPI_IFCR_SUSPC | SPI_IFCR_TSERFC | \
                   SPI_IFCR_OVRC | SPI_IFCR_UDRC | SPI_IFCR_MODFC | SPI_IFCR_TIFREC | SPI_IFCR_CRCEC)

static uint8_t tx[MAX_BYTES] __attribute__((aligned(32)));
static uint8_t rx[MAX_BYTES] __attribute__((aligned(32)));
static uint32_t kernel_hz;
static uint32_t drive_speed = GPIO_SPEED_FREQ_VERY_HIGH;
static uint32_t data_speed = GPIO_SPEED_FREQ_VERY_HIGH;
static uint32_t nss_speed = GPIO_SPEED_FREQ_VERY_HIGH;
static int fill_byte = -1;

typedef struct {
    bool active, master, send, receive, stream;
    unsigned mode, prescaler, width;
    uint32_t size, frames, start_ms, limit_ms, seed, expected;
    uint32_t complete, bad, first_bad, spi_errors, dma_errors;
    uint32_t wraps, submitted, received, elapsed_ms, last_rx_size;
    const char *result;
} Transfer;

static Transfer state = {.result = "idle", .first_bad = UINT32_MAX};

static uint8_t pattern(uint32_t i, uint32_t seed)
{
    uint32_t x = (i ^ seed) * UINT32_C(0x9e3779b1);
    return (uint8_t)(x ^ (x >> 13) ^ (x >> 23));
}

static void pins_at_speed(unsigned mask, uint32_t mode, uint32_t pull, uint32_t speed)
{
    GPIO_InitTypeDef cfg = {
        .Pin = mask, .Mode = mode, .Pull = pull,
        .Speed = speed, .Alternate = 5,
    };
    HAL_GPIO_Init(GPIOI, &cfg);
}

static void pins(unsigned mask, uint32_t mode, uint32_t pull)
{
    if (mask & SCK)
        pins_at_speed(SCK, mode, pull, drive_speed);
    if (mask & (MOSI | MISO))
        pins_at_speed(mask & (MOSI | MISO), mode, pull, data_speed);
    if (mask & NSS)
        pins_at_speed(NSS, mode, pull, nss_speed);
}

static void release_pins(void)
{
    pins(SCK | MISO | MOSI, GPIO_MODE_INPUT, GPIO_NOPULL);
    pins(NSS, GPIO_MODE_INPUT, GPIO_PULLUP);
}

bool spi_fixture_init(void)
{
    __HAL_RCC_GPIOI_CLK_ENABLE();
    release_pins();
    RCC_PeriphCLKInitTypeDef clock = {
        .PeriphClockSelection = RCC_PERIPHCLK_SPI2,
        .Spi123ClockSelection = RCC_SPI123CLKSOURCE_PLL2,
        .PLL2 = {
            .PLL2M = 5, .PLL2N = 80, .PLL2P = 2, .PLL2Q = 2, .PLL2R = 2,
            .PLL2RGE = RCC_PLL2VCIRANGE_2, .PLL2VCOSEL = RCC_PLL2VCOWIDE,
        },
    };
    if (HAL_RCCEx_PeriphCLKConfig(&clock) != HAL_OK)
        return false;
    kernel_hz = HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_SPI2);
    if (kernel_hz != 200000000u)
        return false;
    __HAL_RCC_SPI2_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();
    DMAMUX1_Channel0->CCR = DMA_REQUEST_SPI2_RX;
    DMAMUX1_Channel1->CCR = DMA_REQUEST_SPI2_TX;
    return true;
}

static void dma_disable(DMA_Stream_TypeDef *stream)
{
    stream->CR &= ~DMA_SxCR_EN;
    while (stream->CR & DMA_SxCR_EN) {}
}

static void dma_config(DMA_Stream_TypeDef *stream, uint32_t peripheral, uint8_t *buffer,
                       unsigned count, unsigned width, uint32_t options)
{
    dma_disable(stream);
    stream->PAR = peripheral;
    stream->M0AR = (uint32_t)(uintptr_t)buffer;
    stream->NDTR = count;
    /* Buffer TX requests before the peripheral starts consuming SPI data. */
    stream->FCR = options & DMA_SxCR_DIR_0 ? DMA_SxFCR_DMDIS | DMA_SxFCR_FTH : 0;
    stream->CR = DMA_SxCR_PL | DMA_SxCR_MINC | options |
                 (width == 4 ? DMA_SxCR_MSIZE_1 | DMA_SxCR_PSIZE_1 : 0);
    __DMB();
    stream->CR |= DMA_SxCR_EN;
}

static void start_frame(void)
{
    /* Soft NSS must already be inactive when CFG2 sets MASTER. */
    SPI2->CR1 = state.master ? SPI_CR1_SSI : 0;
    SPI2->IFCR = SPI_CLEAR;
    DMA1->LIFCR = (DMA_ALL << RX_SHIFT) | (DMA_ALL << TX_SHIFT);
    SPI2->CR2 = state.stream ? 0 : state.size;
    SPI2->CFG1 = 7u | ((state.width - 1u) << SPI_CFG1_FTHLV_Pos) |
                 (state.prescaler << SPI_CFG1_MBR_Pos) |
                 (state.receive ? SPI_CFG1_RXDMAEN : 0) | (state.send ? SPI_CFG1_TXDMAEN : 0);
    uint32_t communication = state.send && state.receive ? 0 : state.send ? 1 : 2;
    SPI2->CFG2 = (communication << SPI_CFG2_COMM_Pos) |
                 ((state.mode & 1u) ? SPI_CFG2_CPHA : 0) |
                 ((state.mode & 2u) ? SPI_CFG2_CPOL : 0) |
                 (state.master ? SPI_CFG2_MASTER | SPI_CFG2_SSM | SPI_CFG2_AFCNTR : 0);
    if (state.receive)
        dma_config(DMA1_Stream0, (uint32_t)(uintptr_t)&SPI2->RXDR, rx, state.size / state.width,
                   state.width, 0);
    if (state.send)
        dma_config(DMA1_Stream1, (uint32_t)(uintptr_t)&SPI2->TXDR, tx, state.size / state.width,
                   state.width, DMA_SxCR_DIR_0 | (state.stream ? DMA_SxCR_CIRC : 0));
    if (state.master) {
        SPI2->CR1 |= SPI_CR1_SPE;
        pins(SCK | MOSI, GPIO_MODE_AF_PP, GPIO_NOPULL);
        if (state.receive)
            pins(MISO, GPIO_MODE_AF_PP, GPIO_NOPULL);
        GPIOI->BSRR = NSS << 16;
        __DSB();
        SPI2->CR1 |= SPI_CR1_CSTART;
    } else {
        pins(SCK | MOSI, GPIO_MODE_AF_PP, GPIO_NOPULL);
        pins(NSS, GPIO_MODE_AF_PP, GPIO_PULLUP);
        if (state.send)
            pins(MISO, GPIO_MODE_AF_PP, GPIO_NOPULL);
        SPI2->CR1 = SPI_CR1_SPE;
    }
}

static void record_dma(bool count_wrap)
{
    uint32_t flags = DMA1->LISR;
    if (state.stream && count_wrap && (flags & (DMA_TC << TX_SHIFT))) {
        DMA1->LIFCR = DMA_TC << TX_SHIFT;
        state.wraps++;
    }
    state.dma_errors |= flags & ((DMA_ERRORS << TX_SHIFT) | (DMA_ERRORS << RX_SHIFT));
    state.spi_errors |= SPI2->SR & SPI_ERRORS;
}

static void stop_frame(bool complete)
{
    if (state.master && !complete && (SPI2->CR1 & SPI_CR1_CSTART)) {
        SPI2->CR1 |= SPI_CR1_CSUSP;
        uint32_t now = HAL_GetTick();
        while (!(SPI2->SR & (SPI_SR_SUSP | SPI_SR_EOT)) && HAL_GetTick() - now < 2u) {}
    }
    if (state.master)
        GPIOI->BSRR = NSS;
    if (state.stream) {
        /* Disabling an active DMA stream raises TCIF even on an incomplete
         * lap. Snapshot the real wraps after CSUSP and before clearing EN. */
        record_dma(true);
        uint32_t remaining = DMA1_Stream1->NDTR;
        if (DMA1->LISR & (DMA_TC << TX_SHIFT)) {
            record_dma(true);
            remaining = DMA1_Stream1->NDTR;
        }
        state.submitted = state.wraps * state.size + state.size - remaining * state.width;
    }
    dma_disable(DMA1_Stream0);
    dma_disable(DMA1_Stream1);
    record_dma(false);
    if (state.send && !state.stream)
        state.submitted += state.size - DMA1_Stream1->NDTR * state.width;
    if (state.receive) {
        uint32_t received = state.size - DMA1_Stream0->NDTR * state.width;
        __DMB();
        for (uint32_t i = 0; i < received; ++i) {
            if (rx[i] != pattern(i, state.expected)) {
                if (!state.bad)
                    state.first_bad = state.received + i;
                state.bad++;
            }
        }
        state.last_rx_size = received;
        state.received += received;
    }
    SPI2->CR1 = 0;
    SPI2->IFCR = SPI_CLEAR;
}

static void finish(const char *result, bool frame_running)
{
    if (frame_running)
        stop_frame(false);
    release_pins();
    state.active = false;
    state.elapsed_ms = HAL_GetTick() - state.start_ms;
    state.result = result;
}

void spi_fixture_poll(void)
{
    if (!state.active)
        return;
    record_dma(true);
    if (state.dma_errors || state.spi_errors) {
        finish("hardware_error", true);
    } else if (!state.stream && (SPI2->SR & SPI_SR_EOT) &&
               (!state.receive || DMA1_Stream0->NDTR == 0)) {
        stop_frame(true);
        state.complete++;
        if (state.complete == state.frames || state.bad || state.dma_errors || state.spi_errors)
            finish(state.bad ? "mismatch" : state.dma_errors || state.spi_errors ? "hardware_error" : "done", false);
        else
            start_frame();
    } else if (HAL_GetTick() - state.start_ms >= state.limit_ms) {
        finish(state.stream ? "done" : "timeout", true);
        if (state.dma_errors || state.spi_errors)
            state.result = "hardware_error";
    }
}

void spi_fixture_disconnect(void)
{
    if (state.active)
        finish("disconnected", true);
}

static void status(char *reply, size_t capacity)
{
    unsigned hz = state.master ? kernel_hz >> (state.prescaler + 1u) : 0;
    snprintf(reply, capacity,
             "SPI state=%s role=%s mode=%u sck_hz=%u frames=%" PRIu32 " tx_dma=%" PRIu32
             " rx=%" PRIu32 " bad=%" PRIu32 " first_bad=%" PRIu32 " spi=0x%" PRIx32
             " dma=0x%" PRIx32 " ms=%" PRIu32 "\r\n",
             state.result, state.master ? "master" : "slave", state.mode, hz, state.complete,
             state.submitted, state.received, state.bad, state.first_bad, state.spi_errors,
             state.dma_errors, state.active ? HAL_GetTick() - state.start_ms : state.elapsed_ms);
}

static void read_prefix(char *reply, size_t capacity)
{
    enum { PREFIX_SIZE = 24 };
    static const char digits[] = "0123456789abcdef";
    char hex[2 * PREFIX_SIZE + 1];
    unsigned count = state.last_rx_size < PREFIX_SIZE ? state.last_rx_size : PREFIX_SIZE;
    for (unsigned i = 0; i < count; ++i) {
        hex[2 * i] = digits[rx[i] >> 4];
        hex[2 * i + 1] = digits[rx[i] & 15u];
    }
    hex[2 * count] = '\0';
    snprintf(reply, capacity, "SPI last_rx=%" PRIu32 " head=%s\r\n", state.last_rx_size, hex);
}

static bool number(const char *arg, uint32_t *value)
{
    if (!arg || !*arg || *arg == '-')
        return false;
    char *end;
    unsigned long long parsed = strtoull(arg, &end, 0);
    if (*end || parsed > UINT32_MAX)
        return false;
    *value = (uint32_t)parsed;
    return true;
}

/* MASTER TX|FD mode div bytes frames timeout_ms tx_seed rx_seed
 * SLAVE  RX|FD mode bytes timeout_ms tx_seed rx_seed
 * STREAM mode div duration_ms seed */
static bool parse(char *line, Transfer *job)
{
    char *arg[10], *save;
    unsigned count = 0;
    for (char *token = strtok_r(line, " \t", &save); token; token = strtok_r(NULL, " \t", &save)) {
        if (count == sizeof arg / sizeof arg[0])
            return false;
        arg[count++] = token;
    }
    if (count < 2 || strcmp(arg[0], "SPI"))
        return false;
    job->stream = !strcmp(arg[1], "STREAM");
    job->master = job->stream || !strcmp(arg[1], "MASTER");
    if (!job->master && strcmp(arg[1], "SLAVE"))
        return false;
    if (count != (job->stream ? 6u : job->master ? 10u : 8u))
        return false;
    bool duplex = !job->stream && !strcmp(arg[2], "FD");
    if (!job->stream && !duplex && strcmp(arg[2], job->master ? "TX" : "RX"))
        return false;
    job->send = job->master || duplex;
    job->receive = !job->master || duplex;
    uint32_t mode, divider = 2;
    unsigned pos = job->stream ? 2u : 3u;
    if (!number(arg[pos++], &mode) || mode > 3)
        return false;
    job->mode = mode;
    if (job->master && (!number(arg[pos++], &divider) || divider < 2 || divider > 256 || (divider & (divider - 1))))
        return false;
    for (; divider > 2; divider >>= 1)
        job->prescaler++;
    job->size = STREAM_BYTES;
    job->frames = 1;
    if (!job->stream && (!number(arg[pos++], &job->size) || !job->size || job->size > MAX_BYTES))
        return false;
    if (job->master && !job->stream && (!number(arg[pos++], &job->frames) || !job->frames))
        return false;
    if (!number(arg[pos++], &job->limit_ms) || !job->limit_ms || job->limit_ms > MAX_MS ||
        !number(arg[pos++], &job->seed) || (!job->stream && !number(arg[pos], &job->expected)))
        return false;
    job->width = (job->size & 3u) ? 1 : 4;
    job->first_bad = UINT32_MAX;
    return true;
}

void spi_fixture_command(char *line, char *reply, size_t capacity)
{
    if (!strcmp(line, "PING")) {
        snprintf(reply, capacity, "PONG H743SPI/1\r\n");
    } else if (!strcmp(line, "SPI INFO")) {
        snprintf(reply, capacity, "H743SPI/1 kernel_hz=%" PRIu32
                 " div=2,4,8,16,32,64,128,256 max_bytes=%u max_ms=%u revision=4 drive=%" PRIu32 "\r\n",
                 kernel_hz, MAX_BYTES, MAX_MS, drive_speed);
    } else if (!strcmp(line, "SPI STATUS")) {
        status(reply, capacity);
    } else if (!strcmp(line, "SPI STOP")) {
        if (state.active)
            finish("stopped", true);
        status(reply, capacity);
    } else if (state.active) {
        snprintf(reply, capacity, "ERR busy\r\n");
    } else if (!strncmp(line, "SPI DRIVE ", 10)) {
        uint32_t speed;
        if (!number(line + 10, &speed) || speed > GPIO_SPEED_FREQ_VERY_HIGH) {
            snprintf(reply, capacity, "ERR invalid_drive\r\n");
        } else {
            drive_speed = data_speed = nss_speed = speed;
            snprintf(reply, capacity, "SPI drive=%" PRIu32 "\r\n", drive_speed);
        }
    } else if (!strcmp(line, "SPI EDGE") || !strncmp(line, "SPI EDGE ", 9)) {
        bool valid = true;
        if (line[8] == ' ') {
            char *next;
            uint32_t sck, data, nss;
            char *first = strtok_r(line + 9, " ", &next);
            char *second = strtok_r(NULL, " ", &next);
            char *third = strtok_r(NULL, " ", &next);
            valid = number(first, &sck) && number(second, &data) && number(third, &nss) &&
                    !strtok_r(NULL, " ", &next) && sck <= 3 && data <= 3 && nss <= 3;
            if (valid) {
                drive_speed = sck;
                data_speed = data;
                nss_speed = nss;
            }
        }
        if (valid)
            snprintf(reply, capacity, "SPI edge=%lu,%lu,%lu\r\n",
                     (unsigned long)drive_speed, (unsigned long)data_speed, (unsigned long)nss_speed);
        else
            snprintf(reply, capacity, "ERR invalid_edge\r\n");
    } else if (!strcmp(line, "SPI FILL") || !strncmp(line, "SPI FILL ", 9)) {
        uint32_t value;
        if (!strcmp(line, "SPI FILL PATTERN"))
            fill_byte = -1;
        else if (line[8] == ' ' && number(line + 9, &value) && value <= UINT8_MAX)
            fill_byte = (int)value;
        else if (line[8] == ' ') {
            snprintf(reply, capacity, "ERR invalid_fill\r\n");
            return;
        }
        snprintf(reply, capacity, "SPI fill=%d\r\n", fill_byte);
    } else if (!strcmp(line, "SPI READ")) {
        read_prefix(reply, capacity);
    } else if (!strcmp(line, "SPI PINS")) {
        snprintf(reply, capacity, "SPI pins=0x%lx\r\n", (unsigned long)(GPIOI->IDR & SPI_PINS));
    } else {
        Transfer job = {0};
        if (kernel_hz != 200000000u || !parse(line, &job)) {
            snprintf(reply, capacity, "ERR clock_or_command\r\n");
            return;
        }
        if (job.send)
            for (uint32_t i = 0; i < job.size; ++i)
                tx[i] = job.master && fill_byte >= 0 ? (uint8_t)fill_byte : pattern(i, job.seed);
        state = job;
        if (state.master) {
            GPIOI->BSRR = NSS;
            pins(NSS, GPIO_MODE_OUTPUT_PP, GPIO_NOPULL);
        }
        state.active = true;
        state.result = "active";
        state.start_ms = HAL_GetTick();
        start_frame();
        status(reply, capacity);
    }
}
