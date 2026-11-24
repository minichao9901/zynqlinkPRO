#include "fixture.h"

#ifdef TARGET_H743
#include "stm32h743xx.h"
#else
#include "stm32f103xe.h"
#endif

volatile uint32_t g_cpu_hz, g_hclk_hz, g_clock_error, g_fixture_ready;

static bool wait_bits(volatile uint32_t *reg, uint32_t mask, uint32_t expected)
{
    for (uint32_t retry = 800000; retry; --retry)
        if ((*reg & mask) == expected)
            return true;
    return false;
}

uint32_t target_clock_init(void)
{
#ifdef TARGET_H743
    if (SCB->CCR & SCB_CCR_DC_Msk) SCB_DisableDCache();
    SCB_InvalidateICache();
    SCB_EnableICache();
#endif
    RCC->CR |= RCC_CR_HSION;
    if (!wait_bits(&RCC->CR, RCC_CR_HSIRDY, RCC_CR_HSIRDY)) goto failed;
    RCC->CFGR &= ~RCC_CFGR_SW;
    if (!wait_bits(&RCC->CFGR, RCC_CFGR_SWS, 0)) goto failed;
#ifdef TARGET_H743
    RCC->CR &= ~RCC_CR_PLL1ON;
    if (!wait_bits(&RCC->CR, RCC_CR_PLL1RDY, 0)) goto failed;
    /* Preserve and lock the Apollo LDO supply configuration before changing VOS. */
    PWR->CR3 = (PWR->CR3 & ~(PWR_CR3_BYPASS | PWR_CR3_SCUEN)) | PWR_CR3_LDOEN;
    PWR->D3CR |= PWR_D3CR_VOS;
    if (!wait_bits(&PWR->D3CR, PWR_D3CR_VOSRDY, PWR_D3CR_VOSRDY)) goto failed;
    if (FIXTURE_CPU_MHZ == 480) {
        RCC->APB4ENR |= RCC_APB4ENR_SYSCFGEN;
        (void)RCC->APB4ENR;
        SYSCFG->PWRCR |= SYSCFG_PWRCR_ODEN;
        if (!wait_bits(&PWR->D3CR, PWR_D3CR_VOSRDY, PWR_D3CR_VOSRDY)) goto failed;
    }
    FLASH->ACR = (FLASH->ACR & ~0x3fu) | 0x24u;
    RCC->CR |= RCC_CR_HSEON;
    if (!wait_bits(&RCC->CR, RCC_CR_HSERDY, RCC_CR_HSERDY)) goto failed;
    RCC->PLLCKSELR = (RCC->PLLCKSELR & ~0x3f3u) | (5u << 4) | 2u;
    const uint32_t pll_n = FIXTURE_CPU_MHZ == 480 ? 192u : 96u;
    const uint32_t pll_p = FIXTURE_CPU_MHZ == 480 ? 2u : 8u;
    RCC->PLL1DIVR = (pll_n - 1u) | ((pll_p - 1u) << 9) | (1u << 16) | (11u << 24);
    RCC->PLLCFGR = (RCC->PLLCFGR & ~0x7000fu) | 0x70008u;
    RCC->D1CFGR = FIXTURE_CPU_MHZ == 480 ? 0x48u : 0;
    RCC->D2CFGR = FIXTURE_CPU_MHZ == 480 ? 0x440u : 0;
    RCC->D3CFGR = FIXTURE_CPU_MHZ == 480 ? 0x50u : 0;
    RCC->CFGR &= ~RCC_CFGR_TIMPRE;
    RCC->CR |= RCC_CR_PLL1ON;
    if (!wait_bits(&RCC->CR, RCC_CR_PLL1RDY, RCC_CR_PLL1RDY)) goto failed;
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | 3u;
    if (!wait_bits(&RCC->CFGR, RCC_CFGR_SWS, 3u << 3)) goto failed;
#else
    RCC->CR &= ~RCC_CR_PLLON;
    if (!wait_bits(&RCC->CR, RCC_CR_PLLRDY, 0)) goto failed;
    FLASH->ACR = (FLASH->ACR & ~7u) | (1u << 4) | 2u;
    RCC->CR |= RCC_CR_HSEON;
    if (!wait_bits(&RCC->CR, RCC_CR_HSERDY, RCC_CR_HSERDY)) goto failed;
    uint32_t apb1 = FIXTURE_CPU_MHZ == 128 ? 5u : 4u;
    uint32_t apb2 = FIXTURE_CPU_MHZ == 128 ? 4u : 0u;
    RCC->CFGR = (apb1 << 8) | (apb2 << 11) | (3u << 14) | (1u << 16) |
                ((FIXTURE_CPU_MHZ / 8u - 2u) << 18);
    RCC->CR |= RCC_CR_PLLON;
    if (!wait_bits(&RCC->CR, RCC_CR_PLLRDY, RCC_CR_PLLRDY)) goto failed;
    RCC->CFGR |= 2u;
    if (!wait_bits(&RCC->CFGR, RCC_CFGR_SWS, 2u << 2)) goto failed;
#endif
    g_cpu_hz = FIXTURE_CPU_MHZ * 1000000u;
    g_hclk_hz = FIXTURE_HCLK_MHZ * 1000000u;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    return g_cpu_hz;
failed:
    g_clock_error = 1;
    return 0;
}

uint32_t target_tick(void) { return DWT->CYCCNT; }
uint32_t target_tick_hz(void) { return g_cpu_hz; }

bool uart_configure(uint32_t baud)
{
#ifdef TARGET_H743
    const uint32_t peripheral_hz = FIXTURE_HCLK_MHZ * 500000u;
#else
    const uint32_t peripheral_hz = FIXTURE_HCLK_MHZ * 1000000u;
#endif
    if (!baud || baud > peripheral_hz / 16u) return false;
    uint32_t divisor = (peripheral_hz + baud / 2u) / baud;
    if (divisor < 16 || divisor > 65535) return false;
#ifdef TARGET_H743
    RCC->AHB4ENR |= RCC_AHB4ENR_GPIOAEN;
    RCC->APB2ENR |= RCC_APB2ENR_USART1EN;
    RCC->D2CCIP2R &= ~RCC_D2CCIP2R_USART16SEL;
    (void)RCC->APB2ENR;
    if ((USART1->CR1 & USART_CR1_UE) && !(USART1->ISR & USART_ISR_TC)) return false;
    USART1->CR1 = 0;
    GPIOA->MODER = (GPIOA->MODER & ~(15u << 18)) | (10u << 18);
    GPIOA->AFR[1] = (GPIOA->AFR[1] & ~0xff0u) | 0x770u;
    GPIOA->OSPEEDR |= 15u << 18;
    GPIOA->PUPDR = (GPIOA->PUPDR & ~(15u << 18)) | (1u << 20);
#else
    RCC->APB2ENR |= RCC_APB2ENR_IOPAEN | RCC_APB2ENR_USART1EN;
    (void)RCC->APB2ENR;
    if ((USART1->CR1 & USART_CR1_UE) && !(USART1->SR & USART_SR_TC)) return false;
    USART1->CR1 = 0;
    GPIOA->CRH = (GPIOA->CRH & ~0xff0u) | 0x4b0u;
#endif
    USART1->CR2 = 0;
    USART1->CR3 = 0;
    USART1->BRR = divisor;
    USART1->CR1 = USART_CR1_UE | USART_CR1_RE | USART_CR1_TE;
    return true;
}

bool uart_receive(uint8_t *byte, uint32_t *errors)
{
#ifdef TARGET_H743
    uint32_t status = USART1->ISR;
    *errors = status & 15u;
    if (*errors) USART1->ICR = *errors;
    if (!(status & USART_ISR_RXNE_RXFNE)) return false;
    *byte = USART1->RDR;
#else
    uint32_t status = USART1->SR;
    *errors = status & 15u;
    if (!(status & (USART_SR_RXNE | 15u))) return false;
    *byte = USART1->DR;
    if (!(status & USART_SR_RXNE)) return false;
#endif
    return true;
}

bool uart_send(uint8_t byte)
{
#ifdef TARGET_H743
    if (!(USART1->ISR & USART_ISR_TXE_TXFNF)) return false;
    USART1->TDR = byte;
#else
    if (!(USART1->SR & USART_SR_TXE)) return false;
    USART1->DR = byte;
#endif
    return true;
}

void enable_swo_pin(void)
{
#ifdef TARGET_H743
    RCC->AHB4ENR |= RCC_AHB4ENR_GPIOBEN;
    (void)RCC->AHB4ENR;
    GPIOB->AFR[0] &= ~(15u << 12);
    GPIOB->OSPEEDR |= 3u << 6;
    GPIOB->MODER = (GPIOB->MODER & ~(3u << 6)) | (2u << 6);
    DBGMCU->CR |= 1u << 20; /* TRACECLKEN */
#else
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPBEN;
    (void)RCC->APB2ENR;
    AFIO->MAPR = 2u << 24;
    DBGMCU->CR = (DBGMCU->CR & ~(3u << 6)) | (1u << 5);
#endif
}
