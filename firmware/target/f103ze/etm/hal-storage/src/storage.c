#include "storage.h"
#include "SEGGER_RTT.h"
#include <string.h>

volatile storage_status_t g_storage = {.magic = 0x53544f52, .version = 1};
uint8_t storage_flash_backup[4096], storage_eeprom_backup[256];
static uint8_t verify_buffer[4096], flash_pattern[512], eeprom_pattern[29];
static SPI_HandleTypeDef spi;
static I2C_HandleTypeDef i2c;

static uint32_t checksum(const uint8_t *data, uint32_t n) {
    uint32_t crc = 2166136261u;
    while (n--) { crc ^= *data++; crc *= 16777619u; }
    return crc;
}
static int failed(uint32_t code, uint32_t hal) {
    if (!g_storage.error) g_storage.error = code;
    g_storage.last_hal_error = hal;
    return -1;
}
static void cs(GPIO_PinState level) { HAL_GPIO_WritePin(GPIOB, GPIO_PIN_12, level); }
static int spi_tx(const uint8_t *bytes, uint16_t n) {
    g_storage.spi_calls++;
    HAL_StatusTypeDef rc = HAL_SPI_Transmit(&spi, (uint8_t *)bytes, n, 100);
    return rc == HAL_OK ? 0 : failed(0x101, HAL_SPI_GetError(&spi));
}
static int spi_rx(uint8_t *bytes, uint16_t n) {
    g_storage.spi_calls++;
    HAL_StatusTypeDef rc = HAL_SPI_Receive(&spi, bytes, n, 100);
    return rc == HAL_OK ? 0 : failed(0x102, HAL_SPI_GetError(&spi));
}
static int nor_status(uint8_t *value) {
    const uint8_t command = 0x05;
    cs(GPIO_PIN_RESET);
    int rc = spi_tx(&command, 1);
    if (!rc) rc = spi_rx(value, 1);
    cs(GPIO_PIN_SET);
    return rc;
}
static int nor_ready(uint32_t timeout) {
    uint32_t start = HAL_GetTick();
    uint8_t status;
    do {
        if (nor_status(&status)) return -1;
        if (!(status & 1)) return 0;
    } while ((uint32_t)(HAL_GetTick() - start) < timeout);
    return failed(0x103, status);
}
static int nor_write_enable(void) {
    uint8_t status;
    if (nor_ready(2000) || nor_status(&status)) return -1;
    /* Do not clear protection/status bits on an unknown board. */
    if (status & 0x1c) return failed(0x104, status);
    const uint8_t command = 0x06;
    cs(GPIO_PIN_RESET); int rc = spi_tx(&command, 1); cs(GPIO_PIN_SET);
    if (rc || nor_status(&status)) return -1;
    return status & 2 ? 0 : failed(0x105, status);
}
__attribute__((noinline)) static int nor_read(uint32_t address, uint8_t *data, uint16_t n) {
    if (address + n > g_storage.flash_bytes) return failed(0x106, address);
    uint8_t header[] = {0x03, address >> 16, address >> 8, address};
    cs(GPIO_PIN_RESET); int rc = spi_tx(header, sizeof(header));
    if (!rc) rc = spi_rx(data, n);
    cs(GPIO_PIN_SET); return rc;
}
__attribute__((noinline)) static int nor_erase_sector(uint32_t address) {
    if (address != g_storage.sector_address || (address & 4095)) return failed(0x107, address);
    if (nor_write_enable()) return -1;
    uint8_t header[] = {0x20, address >> 16, address >> 8, address};
    cs(GPIO_PIN_RESET); int rc = spi_tx(header, sizeof(header)); cs(GPIO_PIN_SET);
    return rc ? rc : nor_ready(2000);
}
__attribute__((noinline)) static int nor_program(uint32_t address, const uint8_t *data, uint16_t n) {
    if (address < g_storage.sector_address || address + n > g_storage.sector_address + 4096) return failed(0x108, address);
    while (n) {
        uint16_t take = 256 - (address & 255);
        if (take > n) take = n;
        if (nor_write_enable()) return -1;
        uint8_t header[] = {0x02, address >> 16, address >> 8, address};
        cs(GPIO_PIN_RESET); int rc = spi_tx(header, sizeof(header));
        if (!rc) rc = spi_tx(data, take);
        cs(GPIO_PIN_SET);
        if (rc || nor_ready(100)) return -1;
        address += take; data += take; n -= take;
    }
    return 0;
}
__attribute__((noinline)) static int eeprom_read(uint8_t address, uint8_t *data, uint16_t n) {
    if ((uint32_t)address + n > 256) return failed(0x201, address);
    g_storage.i2c_calls++;
    HAL_StatusTypeDef rc = HAL_I2C_Mem_Read(&i2c, 0xa0, address, I2C_MEMADD_SIZE_8BIT, data, n, 100);
    return rc == HAL_OK ? 0 : failed(0x202, HAL_I2C_GetError(&i2c));
}
__attribute__((noinline)) static int eeprom_write(uint8_t address, const uint8_t *data, uint16_t n) {
    if ((uint32_t)address + n > 256) return failed(0x203, address);
    while (n) {
        uint16_t take = 8 - (address & 7);
        if (take > n) take = n;
        g_storage.i2c_calls++;
        HAL_StatusTypeDef rc = HAL_I2C_Mem_Write(&i2c, 0xa0, address, I2C_MEMADD_SIZE_8BIT, (uint8_t *)data, take, 100);
        if (rc != HAL_OK) return failed(0x204, HAL_I2C_GetError(&i2c));
        /* 24C02 page write cycle is bounded before any next page transfer. */
        HAL_Delay(6);
        if (HAL_I2C_IsDeviceReady(&i2c, 0xa0, 3, 10) != HAL_OK) return failed(0x205, HAL_I2C_GetError(&i2c));
        address += take; data += take; n -= take;
    }
    return 0;
}

void storage_init(void) {
    __HAL_RCC_GPIOB_CLK_ENABLE(); __HAL_RCC_SPI2_CLK_ENABLE(); __HAL_RCC_I2C1_CLK_ENABLE();
    GPIO_InitTypeDef pin = {0};
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_12, GPIO_PIN_SET);
    pin.Pin = GPIO_PIN_12; pin.Mode = GPIO_MODE_OUTPUT_PP; pin.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOB, &pin);
    pin.Pin = GPIO_PIN_13 | GPIO_PIN_15; pin.Mode = GPIO_MODE_AF_PP;
    HAL_GPIO_Init(GPIOB, &pin);
    pin.Pin = GPIO_PIN_14; pin.Mode = GPIO_MODE_INPUT; pin.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOB, &pin);
    pin.Pin = GPIO_PIN_6 | GPIO_PIN_7; pin.Mode = GPIO_MODE_AF_OD;
    HAL_GPIO_Init(GPIOB, &pin);
    spi.Instance = SPI2; spi.Init.Mode = SPI_MODE_MASTER;
    spi.Init.Direction = SPI_DIRECTION_2LINES; spi.Init.DataSize = SPI_DATASIZE_8BIT;
    spi.Init.CLKPolarity = SPI_POLARITY_LOW; spi.Init.CLKPhase = SPI_PHASE_1EDGE;
    spi.Init.NSS = SPI_NSS_SOFT; spi.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;
    spi.Init.FirstBit = SPI_FIRSTBIT_MSB; spi.Init.TIMode = SPI_TIMODE_DISABLE;
    spi.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE; spi.Init.CRCPolynomial = 7;
    if (HAL_SPI_Init(&spi) != HAL_OK) failed(0x301, HAL_SPI_GetError(&spi));
    i2c.Instance = I2C1; i2c.Init.ClockSpeed = 100000;
    i2c.Init.DutyCycle = I2C_DUTYCYCLE_2; i2c.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    i2c.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    i2c.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE; i2c.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
    if (HAL_I2C_Init(&i2c) != HAL_OK) failed(0x302, HAL_I2C_GetError(&i2c));
    storage_identify();
}

int storage_identify(void) {
    uint8_t id[3] = {0}, command = 0x9f;
    cs(GPIO_PIN_RESET); int rc = spi_tx(&command, 1);
    if (!rc) rc = spi_rx(id, 3);
    cs(GPIO_PIN_SET); if (rc) return rc;
    g_storage.jedec = (id[0] << 16) | (id[1] << 8) | id[2];
    if ((id[0] != 0xef && id[0] != 0xc8 && id[0] != 0x85) || id[1] != 0x40 || id[2] < 0x14 || id[2] > 0x18)
        return failed(0x303, g_storage.jedec);
    g_storage.flash_bytes = 1u << id[2];
    g_storage.sector_address = g_storage.flash_bytes - 4096;
    if (HAL_I2C_IsDeviceReady(&i2c, 0xa0, 3, 20) != HAL_OK) return failed(0x304, HAL_I2C_GetError(&i2c));
    return 0;
}

int storage_read_cycle(void) {
    if (!g_storage.flash_bytes || g_storage.error) return -1;
    const uint16_t sizes[] = {1, 2, 3, 17, 256};
    uint16_t n = sizes[g_storage.read_rounds % 5];
    if (nor_read(g_storage.sector_address, verify_buffer, n)) return -1;
    if (eeprom_read(0, verify_buffer + 512, n)) return -1;
    g_storage.test_flash_fnv = checksum(verify_buffer, n);
    g_storage.test_eeprom_fnv = checksum(verify_buffer + 512, n);
    g_storage.read_rounds++;
    return 0;
}

int storage_backup(void) {
    if (g_storage.flash_dirty || g_storage.eeprom_dirty) return failed(0x401, 0);
    g_storage.backup_valid = 0;
    if (storage_identify() || nor_read(g_storage.sector_address, storage_flash_backup, 4096) || eeprom_read(0, storage_eeprom_backup, 256)) return -1;
    if (nor_read(g_storage.sector_address, verify_buffer, 4096) || memcmp(verify_buffer, storage_flash_backup, 4096)) return failed(0x402, 0);
    if (eeprom_read(0, verify_buffer, 256) || memcmp(verify_buffer, storage_eeprom_backup, 256)) return failed(0x403, 0);
    g_storage.flash_backup_fnv = checksum(storage_flash_backup, 4096);
    g_storage.eeprom_backup_fnv = checksum(storage_eeprom_backup, 256);
    g_storage.backup_valid = 1;
    return 0;
}

int storage_restore(void) {
    if (!g_storage.backup_valid || checksum(storage_flash_backup, 4096) != g_storage.flash_backup_fnv || checksum(storage_eeprom_backup, 256) != g_storage.eeprom_backup_fnv)
        return failed(0x404, 0);
    if (g_storage.flash_dirty) {
        if (nor_erase_sector(g_storage.sector_address) || nor_program(g_storage.sector_address, storage_flash_backup, 4096) || nor_read(g_storage.sector_address, verify_buffer, 4096) || memcmp(verify_buffer, storage_flash_backup, 4096)) return failed(0x405, 0);
        g_storage.flash_dirty = 0; g_storage.flash_restored = 1;
    }
    if (g_storage.eeprom_dirty) {
        if (eeprom_write(0, storage_eeprom_backup, 256) || eeprom_read(0, verify_buffer, 256) || memcmp(verify_buffer, storage_eeprom_backup, 256)) return failed(0x406, 0);
        g_storage.eeprom_dirty = 0; g_storage.eeprom_restored = 1;
    }
    return 0;
}

int storage_exercise(void) {
    if (g_storage.arm != STORAGE_ARM || !g_storage.backup_valid) return failed(0x407, 0);
    g_storage.arm = 0;
    if (checksum(storage_flash_backup, 4096) != g_storage.flash_backup_fnv || checksum(storage_eeprom_backup, 256) != g_storage.eeprom_backup_fnv) return failed(0x408, 0);
    for (uint32_t n = 0; n < sizeof(flash_pattern); n++) flash_pattern[n] = (n * 29u + g_storage.write_rounds * 7u + 0x51u) ^ (n >> 3);
    for (uint32_t n = 0; n < sizeof(eeprom_pattern); n++) eeprom_pattern[n] = 0xa5u ^ (n * 13u + g_storage.write_rounds);
    g_storage.flash_restored = g_storage.eeprom_restored = 0;
    int rc = -1;
    g_storage.flash_dirty = 1;
    if (nor_erase_sector(g_storage.sector_address) || nor_program(g_storage.sector_address + 0xf0, flash_pattern, sizeof(flash_pattern)) || nor_read(g_storage.sector_address + 0xf0, verify_buffer, sizeof(flash_pattern))) goto cleanup;
    if (memcmp(verify_buffer, flash_pattern, sizeof(flash_pattern))) { failed(0x409, 0); goto cleanup; }
    g_storage.test_flash_fnv = checksum(verify_buffer, sizeof(flash_pattern));
    g_storage.eeprom_dirty = 1;
    if (eeprom_write(0xdb, eeprom_pattern, sizeof(eeprom_pattern)) || eeprom_read(0xdb, verify_buffer, sizeof(eeprom_pattern))) goto cleanup;
    if (memcmp(verify_buffer, eeprom_pattern, sizeof(eeprom_pattern))) { failed(0x40a, 0); goto cleanup; }
    g_storage.test_eeprom_fnv = checksum(verify_buffer, sizeof(eeprom_pattern));
    g_storage.verified_rounds++; rc = 0;
cleanup:
    if (storage_restore()) rc = -1;
    g_storage.write_rounds++;
    return rc;
}

void storage_dispatch(void) {
    uint32_t command = g_storage.command;
    if (!command) return;
    g_storage.command = 0; g_storage.last_command = command;
    g_storage.state = command; g_storage.error = 0;
    switch (command) {
        case 1: storage_identify(); storage_read_cycle(); break;
        case 2: storage_backup(); break;
        case 3: storage_exercise(); break;
        case 4: storage_restore(); break;
        default: failed(0x40b, command); break;
    }
    g_storage.ack++; g_storage.state = 0;
    SEGGER_RTT_printf(0, "storage cmd=%u ack=%u error=%x writes=%u verified=%u restored=%u/%u\n", command, g_storage.ack, g_storage.error, g_storage.write_rounds, g_storage.verified_rounds, g_storage.flash_restored, g_storage.eeprom_restored);
}
