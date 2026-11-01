`timescale 1ns/1ps
module tb_orbtrace_lane_delay;
  reg clk=0;always #4.166 clk=!clk;
  reg refclk=0;always #2.5 refclk=!refclk;
  reg rst_n=0,calibrated=0,active=0,apply=0,malformed=0;
  reg [25:0] requested=0;reg [4:0] pads=0;
  wire [4:0] sampled;wire ready,ready_ref,busy;wire [31:0] status,accepted,rejected,failures;
  wire [25:0] applied;
  orbtrace_lane_delay dut(.clk(clk),.rst_n(rst_n),.ref_clk(refclk),.calibrated(calibrated),
    .active(active),.apply(apply),.malformed(malformed),.requested(requested),.pads(pads),
    .sampled_pads(sampled),.ready(ready),.ready_ref(ready_ref),.busy(busy),.status(status),.applied(applied),
    .accepted(accepted),.rejected(rejected),.load_failures(failures));
  task command(input [25:0] value);
    begin @(negedge clk);requested=value;apply=1;@(negedge clk);apply=0;end
  endtask
  task settle;
    begin repeat(24)@(negedge clk);end
  endtask
  realtime edge_start;
  task check_edge(input integer lane,input realtime expected);
    realtime delta;
    begin @(posedge sampled[lane]);delta=$realtime-edge_start;
      if(delta<expected-0.002 || delta>expected+0.002)$fatal(1,"lane %0d delay=%0f expected=%0f",lane,delta,expected);
    end
  endtask
  reg [25:0] selected;
  initial begin
    #80;rst_n=1;settle();if(ready || ready_ref)$fatal(1,"not calibrated yet");
    calibrated=1;wait(dut.state==1);@(negedge refclk);calibrated=0;settle();
    if(ready || !status[4])$fatal(1,"startup LD readiness failure was hidden");
    calibrated=1;settle();command(0);settle();if(!ready || status[4] || accepted!=1)$fatal(1,"explicit startup recovery failed");
    // Reset the fixture counters after proving recovery, then check normal boot.
    rst_n=0;#20;rst_n=1;settle();if(!ready || applied || !status[3] || accepted)$fatal(1,"startup zero tap was not explicitly loaded");
    pads=5'b10101;#0.001;if(sampled===pads)$fatal(1,"zero tap falsely treated as no insertion delay");#1;if(sampled!==pads)$fatal(1,"zero tap input pads=%b sampled=%b counts=%h",pads,sampled,dut.counts);pads=0;#5;
    // TRACECLK is stopped throughout this transaction. Only REFCLK is required.
    selected={1'b1,5'd31,5'd16,5'd7,5'd3,5'd0};command(selected);settle();
    if(!ready || !status[3] || applied!==selected || accepted!=1 || failures)$fatal(1,"independent tap load/readback");
    fork
      begin #1;edge_start=$realtime;pads=31;end
      check_edge(0,0.600);check_edge(1,0.834);check_edge(2,1.146);check_edge(3,1.848);check_edge(4,3.018);
    join
    pads=0;#10;
    active=1;command(0);settle();if(rejected!=1 || applied!==selected || accepted!=1)$fatal(1,"capture changed taps");active=0;
    @(negedge clk);malformed=1;@(negedge clk);malformed=0;settle();if(rejected!=2)$fatal(1,"bad key/strobe was accepted");
    command({1'b1,25'd0});command(0);settle();if(rejected!=3 || accepted!=2 || applied!={1'b1,25'd0})$fatal(1,"busy request replaced transaction");
    // A readback mismatch must fail closed and an explicit fresh load recovers it.
    force dut.lane[2].delay.tap=5'd31;
    command({1'b1,25'd0});settle();if(ready || !status[4] || failures!=1)$fatal(1,"bad CNTVALUEOUT falsely passed");
    release dut.lane[2].delay.tap;
    command(selected);settle();if(!ready || status[4] || applied!==selected || accepted!=4)$fatal(1,"explicit recovery failed");
    // Capture preparation resets IDELAYCTRL; selected counts must survive it.
    calibrated=0;settle();if(ready || ready_ref)$fatal(1,"RDY loss ignored");
    command(0);settle();if(rejected!=4)$fatal(1,"load while uncalibrated accepted");
    calibrated=1;settle();if(!ready || applied!==selected)$fatal(1,"controller calibration reset destroyed selected taps");
    // RDY can also disappear during a load: ack the failure once, never replay.
    command({1'b1,25'd0});wait(dut.state==1);@(negedge refclk);calibrated=0;settle();
    if(busy || ready || failures!=2 || !status[4])$fatal(1,"in-flight RDY failure not retired safely");
    calibrated=1;settle();if(ready)$fatal(1,"failed load silently recovered without a new command");
    command(0);settle();if(!ready || applied || status[4] || accepted!=6)$fatal(1,"explicit zero tap restore failed");
    $display("PASS lane delay: independent physical timing, stopped TRACECLK, busy/active/key guards, readback failure, RDY failure, explicit recovery");$finish;
  end
  initial begin #100000;$fatal(1,"timeout");end
endmodule
