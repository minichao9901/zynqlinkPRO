/* STM32F103ZE Elite board: a HAL SPI2 + I2C1 trace workload. */
#include "storage.h"
#include "SEGGER_RTT.h"

void HAL_MspInit(void) {
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_AFIO_REMAP_SWJ_NOJTAG();
}

static void clock_init(void) {
    RCC_OscInitTypeDef osc = {0};
    RCC_ClkInitTypeDef clk = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = RCC_HSE_ON;
    osc.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLMUL = RCC_PLL_MUL6;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) for (;;) {}
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV2;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_1) != HAL_OK) for (;;) {}
    SystemCoreClockUpdate();
}

void SysTick_Handler(void) {
    HAL_IncTick();
    g_storage.ticks++;
}
void HardFault_Handler(void) { g_storage.error = 0x48465254; for (;;) {} }
void NMI_Handler(void) { for (;;) {} }
/* The shared CDC startup intentionally has strong USB vector references. */
void USB_HP_CAN1_TX_IRQHandler(void) { g_storage.error = 0x49525131; }
void USB_LP_CAN1_RX0_IRQHandler(void) { g_storage.error = 0x49525132; }

int main(void) {
    HAL_Init();
    clock_init();
    __HAL_RCC_GPIOE_CLK_ENABLE();
    GPIO_InitTypeDef pins = {0};
    pins.Pin = GPIO_PIN_2 | GPIO_PIN_3 | GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6;
    pins.Mode = GPIO_MODE_AF_PP;
    pins.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOE, &pins);
    SEGGER_RTT_Init();
    SEGGER_RTT_WriteString(0, "F103ZE HAL SPI2 NOR / I2C1 24C02; CPU48 TRACE24; read-only startup\n");
    storage_init();
    g_storage.ready = 1;
    uint32_t last = HAL_GetTick();
    for (;;) {
        storage_dispatch();
        if ((uint32_t)(HAL_GetTick() - last) >= 100) {
            last = HAL_GetTick();
            if (!g_storage.flash_dirty && !g_storage.eeprom_dirty) storage_read_cycle();
        }
        /* Keep this example a continuously traceable workload.  Sleep/STOP
         * behavior needs its own debug-access acceptance and is not tested here. */
        __NOP();
    }
}
