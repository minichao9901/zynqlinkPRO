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

module IDELAYCTRL (input REFCLK, input RST, output RDY);
  reg rdy = 1'b0;
  initial begin #200; rdy = 1'b1; end
  assign RDY = rdy;
endmodule

module IDELAYE2 #(
  parameter IDELAY_TYPE = "VAR_LOAD",
  parameter DELAY_SRC = "IDATAIN",
  parameter IDELAY_VALUE = 0,
  parameter REFCLK_FREQUENCY = 200.0,
  parameter HIGH_PERFORMANCE_MODE = "TRUE",
  parameter SIGNAL_PATTERN = "DATA",
  parameter PIPE_SEL = "FALSE"
) (
  input  IDATAIN,
  input  DATAIN,
  input  C,
  input  CE,
  input  INC,
  input  LD,
  input  LDPIPEEN,
  input  CINVCTRL,
  input  REGRST,
  input  [4:0] CNTVALUEIN,
  output [4:0] CNTVALUEOUT,
  output DATAOUT
);
  reg [4:0] taps = IDELAY_VALUE;
  always @(posedge C) if (LD) taps <= CNTVALUEIN;
  assign CNTVALUEOUT = taps;
  // One tap is 78 ps at a 200 MHz reference clock.
  reg dout = 1'b0;
  always @(IDATAIN) dout <= #(taps * 0.078 + 0.001) IDATAIN; // +1 ps avoids zero-delay loops
  assign DATAOUT = dout;
endmodule
