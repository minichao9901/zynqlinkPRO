// OpenOCD 9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a
export const upstreamFlashConfigs = {
  "stm32f103": [
    "target/stm32f1x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32f0": [
    "target/stm32f0x.cfg",
    "mem_helper.tcl"
  ],
  "stm32f2": [
    "target/stm32f2x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32f3": [
    "target/stm32f3x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32f4": [
    "target/stm32f4x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32f7": [
    "target/stm32f7x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32g0": [
    "target/stm32g0x.cfg",
    "mem_helper.tcl"
  ],
  "stm32g4": [
    "target/stm32g4x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32h7": [
    "target/stm32h7x_dual_bank.cfg",
    "target/stm32h7x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32h7b0": [
    "target/stm32h7x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32l0": [
    "target/stm32l0.cfg",
    "mem_helper.tcl"
  ],
  "stm32l1": [
    "target/stm32l1.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32l4": [
    "target/stm32l4x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32l5": [
    "target/stm32l5x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl",
    "target/stm32x5x_common.cfg"
  ],
  "stm32u5": [
    "target/stm32u5x.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl",
    "target/stm32x5x_common.cfg"
  ],
  "stm32c0": [
    "target/stm32c0x.cfg",
    "mem_helper.tcl"
  ],
  "stm32wb": [
    "target/stm32wbx.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "stm32wl": [
    "target/stm32wlx.cfg",
    "target/swj-dp.tcl",
    "mem_helper.tcl"
  ],
  "nrf52": [
    "target/nordic/nrf52.cfg",
    "mem_helper.tcl"
  ],
  "rp2350": [
    "target/rp2350.cfg"
  ],
  "hpm5300evk": [
    "board/hpmicro/hpm5300evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm5300.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr_lite.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm5301evklite": [
    "board/hpmicro/hpm5301evklite.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm5300.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr_lite.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm5e00evk": [
    "board/hpmicro/hpm5e00evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm5e00.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6200evk": [
    "board/hpmicro/hpm6200evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6280-single-core.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6300evk": [
    "board/hpmicro/hpm6300evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6360.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6750evk2": [
    "board/hpmicro/hpm6750evk2.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6750-single-core.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6750evkmini": [
    "board/hpmicro/hpm6750evkmini.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6750-single-core.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6800evk": [
    "board/hpmicro/hpm6800evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6880.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ],
  "hpm6e00evk": [
    "board/hpmicro/hpm6e00evk.cfg",
    "interface/hpmicro/hpmicro_evk.cfg",
    "target/hpmicro/hpm6e80-single-core.cfg",
    "target/hpmicro/hpm_common.cfg",
    "target/hpmicro/hpm_reset.cfg",
    "target/hpmicro/hpm_common_csr.cfg",
    "interface/cmsis-dap.cfg"
  ]
};
