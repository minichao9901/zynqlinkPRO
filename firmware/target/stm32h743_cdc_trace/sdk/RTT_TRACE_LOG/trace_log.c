#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include "trace_log.h"

static uint32_t write_counts = 0;

static char buffer[100];
void do_trace(const char *sfile, const int line, const char *sfunc, const char *fmt, ...)
{
    memset(&buffer[0], ' ', 100); //用空格填充
    snprintf(&buffer[0], 55, "%-16s:%-4d| %-32s", sfile, line, sfunc);
    if (fmt!=NULL) {
        // 字符串跟踪 - 高亮特殊标记
        va_list args;
        va_start(args, fmt);
        vsnprintf(&buffer[55], 44, fmt, args);
        va_end(args);
    }
    buffer[99] = '\n'; 

    SEGGER_RTT_Write(0, buffer, 100);


    write_counts++;
    if(write_counts%1000 == 0)
    {
        char buf[20];
        memset(&buf[0], 0, 20);
        sprintf(buf, "write_counts=%d\n",write_counts);
        SEGGER_RTT_Write(0, buf, strlen(buf));
        memset(&buf[0], 0, 20);
        sprintf(buf, "RTT free=%d\n", SEGGER_RTT_GetAvailWriteSpace(0));
        SEGGER_RTT_Write(0, buf, strlen(buf));
    }
}


void trace_log_init(void) 
{
    SEGGER_RTT_Init();
}
