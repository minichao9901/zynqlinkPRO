"""Guard-page test of the production SWJ serializer, including unaligned tails."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-revision', help='Optional Git source revision for a negative control')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
relative = 'firmware/xusbps_daplink_dma/DAP/Source/SW_DP.c'
source = (subprocess.check_output(['git', 'show', args.source_revision + ':' + relative],
                                  cwd=root).decode('utf-8') if args.source_revision
          else (root / relative).read_text(encoding='utf-8'))
function = source[source.index('static void SWJ_SequenceChunk'):source.index('\nvoid SWJ_Sequence')]
out = root / 'build/test_swj_sequence'
out.mkdir(parents=True, exist_ok=True)
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#include <unistd.h>
#endif
#define SWD_SWJ_DATA0 0x10U
#define SWD_SWJ_DATA1 0x14U
#define SWD_SWJ_DATA2 0x18U
#define SWD_SWJ_DATA3 0x1cU
#define SWD_SWJ_DATA4 0x20U
#define SWD_SWJ_DATA5 0x24U
#define SWD_SWJ_DATA6 0x28U
#define SWD_SWJ_DATA7 0x2cU
#define SWD_SWJ_COUNT 0x0cU
#define SWD_CTRL 0U
static uint32_t captured[8], count_word, control;
static unsigned writes, waits;
static void swd_write32(uint32_t address, uint32_t value) {
    ++writes;
    if (address >= SWD_SWJ_DATA0 && address < SWD_SWJ_DATA0 + 32)
        captured[(address - SWD_SWJ_DATA0) / 4] = value;
    else if (address == SWD_SWJ_COUNT) count_word = value;
    else { assert(address == SWD_CTRL); control = value; }
}
static void swd_wait_idle(void) { ++waits; }
'''
code += function + r'''
int main(void) {
    size_t page;
    uint8_t *memory;
#ifdef _WIN32
    SYSTEM_INFO info; DWORD previous;
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    GetSystemInfo(&info); page = info.dwPageSize;
    memory = VirtualAlloc(NULL, page * 2, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    assert(memory && VirtualProtect(memory + page, page, PAGE_NOACCESS, &previous));
#else
    page = (size_t)sysconf(_SC_PAGESIZE);
    memory = mmap(NULL, page * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(memory != MAP_FAILED && !mprotect(memory + page, page, PROT_NONE));
#endif
    for (unsigned bits = 1; bits <= 256; ++bits) {
        unsigned bytes = (bits + 7) / 8;
        uint8_t *data = memory + page - bytes;
        for (unsigned n = 0; n < bytes; ++n) data[n] = (uint8_t)(bits + 17 * n);
        memset(captured, 0xa5, sizeof(captured)); writes = waits = 0;
        SWJ_SequenceChunk(bits, data);
        assert(count_word == bits && control == 1 && writes == 10 && waits == 1);
        for (unsigned n = 0; n < 32; ++n)
            assert(((uint8_t *)captured)[n] == (n < bytes ? data[n] : 0));
    }
    puts("PASS: production SWJ 1..256 bits; all packet alignments, guard-page bounds and MMIO words");
    return 0;
}
'''
(out / 'swj_test.c').write_text(code, encoding='utf-8')
compiler = ['gcc']
if os.name == 'nt' and shutil.which('clang') and shutil.which('gcc'):
    mingw = Path(shutil.which('gcc')).parent.parent
    libs = list((mingw / 'lib/gcc/x86_64-w64-mingw32').glob('*'))
    compiler = ['clang', '--target=x86_64-w64-windows-gnu', '-isystem', str(mingw / 'include'),
                '-L' + str(mingw / 'lib'), '-L' + str(libs[-1])]
exe = out / 'swj_test.exe'
subprocess.run([*compiler, '-O3', '-Wall', '-Wextra', '-Werror', str(out / 'swj_test.c'),
                '-o', str(exe)], check=True)
result = subprocess.run([str(exe)], timeout=10)
print('SWJ native execution returncode:', result.returncode, flush=True)
raise SystemExit(result.returncode)
