#ifndef H743_SPI_FIXTURE_H
#define H743_SPI_FIXTURE_H

#include <stdbool.h>
#include <stddef.h>

bool spi_fixture_init(void);
void spi_fixture_poll(void);
void spi_fixture_disconnect(void);
void spi_fixture_command(char *line, char *reply, size_t capacity);

#endif
