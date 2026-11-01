`timescale 1ns/1ps
// Digital path-skew experiment, not an analog cable/BER model. Both runs use
// identical source data and timing; only physical-input delay selection changes.
module tb_orbtrace_lane_sampling;
  reg clk=0;always #4.166 clk=!clk;
  reg refclk=0;always #2.5 refclk=!refclk;
  reg rst_n=0,rx_rst=1,apply=0;reg [25:0] requested=0;
  reg [4:0] source=0;wire [4:0] pads,sampled;
  assign #0.200 pads[0]=source[0];assign #0.800 pads[1]=source[1];
  assign #1.400 pads[2]=source[2];assign #2.000 pads[3]=source[3];assign pads[4]=source[4];
  wire ready,ready_ref;wire [31:0] rejected;
  orbtrace_lane_delay delays(.clk(clk),.rst_n(rst_n),.ref_clk(refclk),.calibrated(1'b1),
    .active(!rx_rst),.apply(apply),.malformed(1'b0),.requested(requested),.pads(pads),
    .sampled_pads(sampled),.ready(ready),.ready_ref(ready_ref),.busy(),.status(),.applied(),
    .accepted(),.rejected(rejected),.load_failures());
  wire [127:0] frame;wire event_frame,parser_error;
  orbtrace_parallel #(.RAW_DIAGNOSTIC(4)) receiver(.clk(clk),.rst(rx_rst),
    .trace_clk(sampled[4]),.trace_io_clk(sampled[4]),.trace_pad_clk(sampled[4]),.sample_clk(refclk),
    .trace_data(sampled[3:0]),.width(2'd3),.ready(1'b1),.data(),.channel(),.valid(),.synced(),.overflow(),
    .diagnostic_reset(rx_rst),.diagnostic_flags(),.dropped_frames(),.parser_errors(),.sync_acquisitions(),.frame_highwater(),
    .ddr_hold(1'b0),.ddr_sampler_gate(1'b0),.ddr_parser_enable(1'b0),.ddr_parser_clear(1'b0),
    .ddr_frame(frame),.ddr_frame_event(event_frame),.ddr_parser_error(parser_error),.ddr_sync_event(),
    .ddr_tail(),.ddr_tail_bytes(),.ddr_tail_ambiguous());
  integer good=0,bad=0,errors=0,before_good,before_bad;
  always @(posedge refclk)begin
    if(rx_rst)begin good=0;bad=0;errors=0;end
    else begin
      if(event_frame)begin if(frame===128'h101112131415161718191a1b1c1d1e1f)good=good+1;else bad=bad+1;end
      if(parser_error)errors=errors+1;
    end
  end
  task put_byte(input [7:0] value);
    begin source={1'b1,value[3:0]};#13.889;source={1'b0,value[7:4]};#13.889;end
  endtask
  task frames;
    begin
      // Identical starting phase in both runs, roughly 36MHz TRACECLK.
      repeat(20)@(negedge refclk);#2.25;
      repeat(3)begin put_byte(8'hff);put_byte(8'hff);put_byte(8'hff);put_byte(8'h7f);end
      for(integer j=0;j<16;j=j+1)for(integer k=0;k<16;k=k+1)put_byte(8'(16+k));
      source=0;repeat(100)@(negedge refclk);
    end
  endtask
  task command(input [25:0] cfg);
    begin @(negedge clk);requested=cfg;apply=1;@(negedge clk);apply=0;repeat(24)@(negedge clk);end
  endtask
  initial begin
    #80;rst_n=1;wait(ready);repeat(10)@(negedge refclk);rx_rst=0;frames();
    before_good=good;before_bad=bad;
    if(good==16 && bad==0)$fatal(1,"zero-tap skew fixture did not exercise a sampling error");
    rx_rst=1;repeat(10)@(negedge refclk);
    // Total modeled arrival time: data about 2.0ns, clock 2.028ns,
    // plus the common 0.6ns delay-element insertion delay.
    command({1'b1,5'd26,5'd0,5'd8,5'd16,5'd23});if(!ready)$fatal(1,"tap load");
    @(negedge refclk);rx_rst=0;
    repeat(20)@(negedge refclk);
    #1;source=31;#1;source=0;#50;
    if(receiver.raw_oversample_filtered.half || receiver.raw_oversample_filtered.stable_clock)$fatal(1,"1ns pulse created a trace edge");
    fork frames();command(0);join
    if(good!=16 || bad || errors || rejected!=1)$fatal(1,"calibrated pin stream good=%0d bad=%0d errors=%0d rejects=%0d",good,bad,errors,rejected);
    $display("PASS lane sampling: same skewed 36MHz-class pins zero_tap_good=%0d zero_tap_bad=%0d adjusted_good=%0d, 1ns glitches rejected, live update blocked",before_good,before_bad,good);$finish;
  end
  initial begin #200000;$fatal(1,"timeout");end
endmodule
