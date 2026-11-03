/* Reuse the versioned repository F1 HAL configuration; add hardware I2C. */
#define HAL_I2C_MODULE_ENABLED
#define USE_HAL_I2C_REGISTER_CALLBACKS 0U
#include "../../stm32f103_cdc_trace/sdk/stm32f1xx_hal_conf.h"
