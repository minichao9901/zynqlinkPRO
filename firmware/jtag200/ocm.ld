ENTRY(_start)
MEMORY {
  OCM (rwx) : ORIGIN = 0, LENGTH = 0x2c000
}
SECTIONS {
  .text : { KEEP(*(.text.start)) *(.text*) } > OCM
  .rodata : { *(.rodata*) } > OCM
  /DISCARD/ : { *(.comment) *(.ARM.attributes) }
  .unused : { *(.data*) *(.bss*) *(COMMON) } > OCM
  ASSERT(SIZEOF(.unused) == 0, "Startup expects no mutable C globals")
}
