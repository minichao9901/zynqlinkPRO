ENTRY(trace_entry)
PHDRS { code PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    . = 0x20000000;
    .text : { KEEP(*(.vectors)) *(.text*) } :code
    .bss (NOLOAD) : { *(.bss*) } :data
    ASSERT(. < 0x20000300, "reserve the last 256 bytes for the exception stack")
}
