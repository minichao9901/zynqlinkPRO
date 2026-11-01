#ifndef TRACE_LOG_H
#define TRACE_LOG_H

#include "SEGGER_RTT.h"

// #define MSG_BUF_SIZE (1024*1024/100)
// #define MSG_BUF_SIZE (8192)
// #define TRACE_LOG_DELAY 10000
#define SRAM_BUFFER_ADDR 0x68000000

/*size=100bytes*/
struct log_msg {
    char file[16]; 
    int line;
    char func[32];
    int var;
    char svar[44];    
}; 

void do_trace(const char *sfile, const int line, const char *sfunc, const char *fmt, ...);
void trace_log_init(void);

#endif
