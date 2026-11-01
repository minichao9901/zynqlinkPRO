/* SRAM-only experiment: vectors/code and initialized-data load image in lower 32KiB; runtime data in upper 32KiB. Never program this image into Flash. */
/*
 * STM32F103ZE SRAM-only CDC/ETM clock experiment (64KiB total SRAM).
 * The Flash image and its linker script are unchanged.
 *
 * 固定地址段（外部 SWD / RTT 工具按约定地址访问）——**不放在 RAM 末尾**：
 *   .rtt_cb      固定低地址        -> SEGGER RTT 控制块
 *   .trace_diag 固定低地址        -> g_trace 诊断变量
 * Runtime data starts at 0x20008000. Fixed diagnostics remain at B000/C000;
 * stack starts at 0x20010000. Lower SRAM stores code and data initializers.
 */
ENTRY(Reset_Handler)

MEMORY
{
  CODE  (rx)  : ORIGIN = 0x20000000, LENGTH = 32K
  RAM   (rwx) : ORIGIN = 0x20008000, LENGTH = 32K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);
_Min_Heap_Size  = 0x200;
_Min_Stack_Size = 0x400;

SECTIONS
{
  .isr_vector : {
    . = ALIGN(4);
    KEEP(*(.isr_vector))
    . = ALIGN(4);
  } > CODE

  .text : {
    . = ALIGN(4);
    *(.text) *(.text*)
    *(.glue_7) *(.glue_7t) *(.eh_frame)
    KEEP(*(.init)) KEEP(*(.fini))
    . = ALIGN(4);
    _etext = .;
  } > CODE

  .rodata : {
    . = ALIGN(4);
    *(.rodata) *(.rodata*)
    . = ALIGN(4);
  } > CODE

  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > CODE
  .ARM : {
    . = ALIGN(4);
    __exidx_start = .;
    *(.ARM.exidx*)
    __exidx_end = .;
    . = ALIGN(4);
  } > CODE

  .preinit_array : {
    PROVIDE_HIDDEN(__preinit_array_start = .);
    KEEP(*(.preinit_array*))
    PROVIDE_HIDDEN(__preinit_array_end = .);
  } > CODE
  .init_array : {
    PROVIDE_HIDDEN(__init_array_start = .);
    KEEP(*(SORT(.init_array.*)))
    KEEP(*(.init_array*))
    PROVIDE_HIDDEN(__init_array_end = .);
  } > CODE
  .fini_array : {
    PROVIDE_HIDDEN(__fini_array_start = .);
    KEEP(*(SORT(.fini_array.*)))
    KEEP(*(.fini_array*))
    PROVIDE_HIDDEN(__fini_array_end = .);
  } > CODE

  _sidata = LOADADDR(.data);

  .data : {
    . = ALIGN(4);
    _sdata = .;
    *(.data) *(.data*)
    . = ALIGN(4);
    _edata = .;
  } > RAM AT> CODE

  . = ALIGN(4);
  .bss : {
    _sbss = .;
    __bss_start__ = _sbss;
    *(.bss) *(.bss*) *(COMMON)
    . = ALIGN(4);
    _ebss = .;
    __bss_end__ = _ebss;
  } > RAM

  ._user_heap_stack : {
    . = ALIGN(8);
    PROVIDE(end = .);
    PROVIDE(_end = .);
    . = . + _Min_Heap_Size;
    . = . + _Min_Stack_Size;
    . = ALIGN(8);
  } > RAM

  /* 固定地址段：外部工具直接按地址读 */
  .trace_diag 0x2000C000 (NOLOAD) : {
    . = ALIGN(4);
    KEEP(*(.trace_diag))
    . = ALIGN(4);
  } > RAM

  .rtt_cb 0x2000B000 (NOLOAD) : {
    . = ALIGN(4);
    KEEP(*(.rtt_cb))
    . = ALIGN(4);
  } > RAM

  /DISCARD/ : { *(.ARM.attributes) }
}

