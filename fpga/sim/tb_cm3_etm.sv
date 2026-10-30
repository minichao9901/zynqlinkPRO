`timescale 1ns/1ps
// Reuse the actual PL SWD controller and MEM-AP BFM, with full CM3 ETM enabled.
module tb_cm3_etm;
  tb_cm3_swd #(.CM3_TRACE_LEVEL(2),.ETM_TEST(1)) bench();
endmodule
