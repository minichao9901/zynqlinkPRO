// Minimal simulation models for the Xilinx primitives used by swd_controller.
// Behaviour matches the OPPOSITE_EDGE IDDR and the tri-state IOBUF; they are
// only for RTL simulation, synthesis still uses the real primitives.
`timescale 1ns/1ps
module BUFG(input I,output O);
  assign O=I;
endmodule
module BUFIO(input I,output O);
  assign O=I;
endmodule
module BUFR #(parameter BUFR_DIVIDE="BYPASS",SIM_DEVICE="7SERIES") (input I,CE,CLR,output O);
  // Exercise nonzero BUFIO -> BUFR skew in the controller's functional tests.
  // This is not a device timing model; routed STA is the timing authority.
  assign #1 O=I && CE && !CLR;
endmodule
module IDELAYCTRL(input REFCLK,RST,output reg RDY=0);
  integer stable=0;
  always @(posedge REFCLK or posedge RST)
    if(RST)begin stable<=0;RDY<=0;end
    else if(stable<64)stable<=stable+1;else RDY<=1;
endmodule
module IDELAYE2 #(
  parameter DELAY_SRC="IDATAIN",IDELAY_TYPE="FIXED",IDELAY_VALUE=0,
  parameter real REFCLK_FREQUENCY=200.0,
  parameter HIGH_PERFORMANCE_MODE="FALSE",SIGNAL_PATTERN="DATA"
)(input IDATAIN,DATAIN,C,CE,INC,LD,LDPIPEEN,REGRST,CINVCTRL,input [4:0] CNTVALUEIN,
  output DATAOUT,output [4:0] CNTVALUEOUT);
  assign #(0.6+IDELAY_VALUE*0.078) DATAOUT=IDATAIN;
  assign CNTVALUEOUT=IDELAY_VALUE;
endmodule

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
  generate if(DDR_CLK_EDGE=="SAME_EDGE_PIPELINED")begin
    reg rise_stage=INIT_Q1,fall_stage=INIT_Q2;
    always @(posedge C or posedge R or posedge S)
      if(R)begin rise_stage<=0;q1<=0;q2<=0;end
      else if(S)begin rise_stage<=1;q1<=1;q2<=1;end
      else if(CE)begin rise_stage<=D;q1<=rise_stage;q2<=fall_stage;end
    always @(negedge C or posedge R or posedge S)
      if(R)fall_stage<=0;else if(S)fall_stage<=1;else if(CE)fall_stage<=D;
  end else if(SRTYPE=="ASYNC")begin
    always @(posedge C or posedge R or posedge S)
      if(R)q1<=0;else if(S)q1<=1;else if(CE)q1<=D;
    always @(negedge C or posedge R or posedge S)
      if(R)q2<=0;else if(S)q2<=1;else if(CE)q2<=D;
  end else begin
    always @(posedge C)if(R)q1<=0;else if(S)q1<=1;else if(CE)q1<=D;
    always @(negedge C)if(R)q2<=0;else if(S)q2<=1;else if(CE)q2<=D;
  end endgenerate
  assign Q1 = q1;
  assign Q2 = q2;
endmodule
