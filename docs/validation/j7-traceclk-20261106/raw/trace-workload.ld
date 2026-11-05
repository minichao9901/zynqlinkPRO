ENTRY(trace_loop)
PHDRS { sram PT_LOAD FLAGS(7); }
SECTIONS {
  . = 0x20000000;
  .vectors : { KEEP(*(.vectors)) } :sram
  .text : { *(.text*) } :sram
  .bss (NOLOAD) : { *(.bss*) } :sram
}
