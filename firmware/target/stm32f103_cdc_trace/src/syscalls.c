/*
 * newlib 最小 syscall 桩 —— 裸机（F103）
 *
 * 只为了让 -specs=nano.specs 的 vsnprintf/字符串函数能链接过。
 * 没有文件系统、没有堆使用（_sbrk 只做"堆顶不越界"的检查）。
 */
#include <errno.h>
#include <stddef.h>
#include <sys/stat.h>
#include <sys/types.h>

extern char _end;   /* 链接脚本提供：堆起点 */
extern char _estack; /* 链接脚本提供：栈顶（RAM 末尾） */

void *_sbrk(ptrdiff_t incr)
{
    static char *heap_end = NULL;
    char *prev;

    if (heap_end == NULL) {
        heap_end = &_end;
    }
    prev = heap_end;

    /* 留 1KB 给栈，超了就返回失败（不真正分配） */
    if (heap_end + incr > (&_estack - 1024)) {
        errno = ENOMEM;
        return (void *)-1;
    }
    heap_end += incr;
    return prev;
}

int _write(int file, char *ptr, int len)
{
    (void)file;
    (void)ptr;
    return len; /* 不接 UART，丢弃 */
}

int _read(int file, char *ptr, int len)
{
    (void)file;
    (void)ptr;
    (void)len;
    return 0;
}

int _close(int file)
{
    (void)file;
    return -1;
}

int _fstat(int file, struct stat *st)
{
    (void)file;
    st->st_mode = S_IFCHR;
    return 0;
}

int _isatty(int file)
{
    (void)file;
    return 1;
}

int _lseek(int file, int ptr, int dir)
{
    (void)file;
    (void)ptr;
    (void)dir;
    return 0;
}

int _getpid(void)
{
    return 1;
}

int _kill(int pid, int sig)
{
    (void)pid;
    (void)sig;
    errno = EINVAL;
    return -1;
}
