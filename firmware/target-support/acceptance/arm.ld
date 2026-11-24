ENTRY(Reset_Handler)

MEMORY {
    IMAGE (rx) : ORIGIN = image_base, LENGTH = image_size
    DATA (rwx) : ORIGIN = data_base, LENGTH = data_size
}

_estack = ORIGIN(DATA) + LENGTH(DATA);
SECTIONS {
    .vectors : { KEEP(*(.vectors)) } > IMAGE
    .text : { *(.text .text.* .rodata .rodata.*) } > IMAGE
    .ARM.extab : { *(.ARM.extab*) } > IMAGE
    .ARM.exidx : {
        __exidx_start = .;
        *(.ARM.exidx*)
        __exidx_end = .;
    } > IMAGE
    .data : {
        . = ALIGN(4); _sdata = .;
        *(.data .data.*)
        . = ALIGN(4); _edata = .;
    } > DATA AT> IMAGE
    _sidata = LOADADDR(.data);
    .bss (NOLOAD) : {
        . = ALIGN(32); _sbss = .;
        *(.bss .bss.* COMMON)
        . = ALIGN(4); _ebss = .;
    } > DATA
    _end = _ebss;
    PROVIDE(end = _end);
    ASSERT(_ebss + 2048 <= _estack, "Fixture data overlaps stack")
}
