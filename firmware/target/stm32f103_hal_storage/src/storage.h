#ifndef HAL_STORAGE_DEMO_H
#define HAL_STORAGE_DEMO_H
#include "stm32f1xx_hal.h"
#include <stdint.h>

/* Mailbox commands: 1 identify/read, 2 backup, 3 test+restore, 4 restore.
 * command 3 requires the explicit arm token and a verified RAM backup.
 * Startup and idle cycles never write external nonvolatile memory. */
#define STORAGE_ARM 0x53545257u
typedef struct {
    uint32_t magic, version, ready, command, ack, state, error, jedec;
    uint32_t flash_bytes, sector_address, backup_valid, arm;
    uint32_t flash_backup_fnv, eeprom_backup_fnv, flash_restored, eeprom_restored;
    uint32_t read_rounds, write_rounds, verified_rounds, spi_calls, i2c_calls;
    uint32_t ticks, last_hal_error, last_command, test_flash_fnv, test_eeprom_fnv;
    uint32_t flash_dirty, eeprom_dirty;
} storage_status_t;
extern volatile storage_status_t g_storage;
extern uint8_t storage_flash_backup[4096], storage_eeprom_backup[256];
void storage_init(void);
int storage_identify(void);
int storage_backup(void);
int storage_exercise(void);
int storage_restore(void);
int storage_read_cycle(void);
void storage_dispatch(void);
#endif
