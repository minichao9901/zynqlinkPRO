// Independent diagnostic: PS GP0 -> AXI GPIO -> two physical SWD pins.
// No production SWD/JTAG FSM, USB, DMA, sampler or clock multiplexer.
module minimal_swd_top(
 inout [14:0] DDR_addr,inout [2:0] DDR_ba,
 inout DDR_cas_n,DDR_ck_n,DDR_ck_p,DDR_cke,DDR_cs_n,
 inout [3:0] DDR_dm,inout [31:0] DDR_dq,
 inout [3:0] DDR_dqs_n,DDR_dqs_p,
 inout DDR_odt,DDR_ras_n,DDR_reset_n,DDR_we_n,
 inout FIXED_IO_ddr_vrn,FIXED_IO_ddr_vrp,
 inout [53:0] FIXED_IO_mio,
 inout FIXED_IO_ps_clk,FIXED_IO_ps_porb,FIXED_IO_ps_srstb,
 inout swclk,inout swdio,output nreset,ntrst
);
 wire [4:0] control;
 wire [11:0] sense;
 wire fabric_clk;
 reg previous_clock=0;
 always @(posedge fabric_clk)begin
  previous_clock<=control[0];
 end
 // At fixed 100MHz FCLK, the diagnostic short mode holds SWCLK high for
 // exactly half a fabric cycle (5ns). Direct and short modes share this
 // same bitstream, pad, output primitive and source routing.
 wire drive_clock;
 wire clock_d1=control[3] ? (control[0] && !previous_clock) : control[0];
 wire clock_d2=control[3] ? 1'b0 : control[0];
 reg intended_hi=0,intended_lo=0;
 always @(posedge fabric_clk)begin
  intended_hi<=clock_d1;intended_lo<=clock_d2;
 end
 // ODDR Q may only feed the pad. Compare feedback with a fabric copy of
 // its requested levels, rather than adding illegal loads to the IOB Q.
 wire intended_clock=fabric_clk ? intended_hi : intended_lo;
 ODDR #(.DDR_CLK_EDGE("SAME_EDGE"),.INIT(1'b0),.SRTYPE("SYNC")) clock_launch(
  .C(fabric_clk),.CE(1'b1),.R(1'b0),.S(1'b0),
  .D1(clock_d1),.D2(clock_d2),.Q(drive_clock));
 (* CLOCK_BUFFER_TYPE="NONE" *)wire clock_feedback;
 wire dio_feedback;
 reg [7:0] pad_rises=0;
 reg fall_while_high=0,rise_while_low=0;
 IOBUF clock_pin(.I(drive_clock),.T(1'b0),.O(clock_feedback),.IO(swclk));
 // Diagnostic only. Snapshot the counter after clocks have stopped; narrow
 // analog pulses below the input/FF specifications can still be missed.
 always @(posedge clock_feedback or posedge control[4])begin
  if(control[4])begin pad_rises<=0;rise_while_low<=0;end
  else begin pad_rises<=pad_rises+1'b1;if(!intended_clock)rise_while_low<=1;end
 end
 always @(negedge clock_feedback or posedge control[4])begin
  if(control[4])fall_while_high<=0;
  else if(intended_clock)fall_while_high<=1;
 end
 assign sense={pad_rises,rise_while_low,fall_while_high,dio_feedback,clock_feedback};
 assign nreset=1'b1;
 assign ntrst=1'b1;
 IOBUF dio(.I(control[1]),.T(control[2]),.O(dio_feedback),.IO(swdio));
 minimal_swd_bd minimal_i(
 .DDR_addr(DDR_addr),.DDR_ba(DDR_ba),.DDR_cas_n(DDR_cas_n),
 .DDR_ck_n(DDR_ck_n),.DDR_ck_p(DDR_ck_p),.DDR_cke(DDR_cke),.DDR_cs_n(DDR_cs_n),
 .DDR_dm(DDR_dm),.DDR_dq(DDR_dq),.DDR_dqs_n(DDR_dqs_n),.DDR_dqs_p(DDR_dqs_p),
 .DDR_odt(DDR_odt),.DDR_ras_n(DDR_ras_n),.DDR_reset_n(DDR_reset_n),.DDR_we_n(DDR_we_n),
 .FIXED_IO_ddr_vrn(FIXED_IO_ddr_vrn),.FIXED_IO_ddr_vrp(FIXED_IO_ddr_vrp),
 .FIXED_IO_mio(FIXED_IO_mio),.FIXED_IO_ps_clk(FIXED_IO_ps_clk),
 .FIXED_IO_ps_porb(FIXED_IO_ps_porb),.FIXED_IO_ps_srstb(FIXED_IO_ps_srstb),
 .control(control),.sense(sense),.fabric_clk(fabric_clk));
endmodule
