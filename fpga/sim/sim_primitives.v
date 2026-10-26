// Minimal simulation models for the Xilinx primitives used by swd_controller.
// Behaviour matches the OPPOSITE_EDGE IDDR and the tri-state IOBUF; they are
// only for RTL simulation, synthesis still uses the real primitives.
`timescale 1ns/1ps

module IOBUF (input I, input T, output O, inout IO);
  assign IO = T ? 1'bz : I;
  assign O  = IO;
endmodule

module IDDR #(
  parameter DDR_CLK_EDGE = "OPPOSITE_EDGE",
  parameter INIT_Q1 = 1'b0,
  parameter INIT_Q2 = 1'b0,
  parameter SRTYPE = "SYNC"
) (
  input  C,
  input  CE,
  input  D,
  input  R,
  input  S,
  output Q1,
  output Q2
);
  reg q1 = INIT_Q1;
  reg q2 = INIT_Q2;
  always @(posedge C) if (CE) q1 <= D;
  always @(negedge C) if (CE) q2 <= D;
  assign Q1 = q1;
  assign Q2 = q2;
endmodule
