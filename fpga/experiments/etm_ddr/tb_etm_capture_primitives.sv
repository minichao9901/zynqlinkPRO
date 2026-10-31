`timescale 1ns/1ps
module tb_etm_capture_primitives #(parameter FIFO_ADDR=3);
  localparam DEPTH=1<<FIFO_ADDR;
  localparam FRAMES=DEPTH<32 ? 1000 : 4*DEPTH+17;
  reg ref_clk=0;always #2.5 ref_clk=!ref_clk;
  reg rst=1,start=0,stop=0;reg [11:0] ticks=0;reg [1:0] stop_reason=1;
  wire active,done,rejected;wire [11:0] elapsed;wire [1:0] reason;
  etm_ref_window #(.WIDTH(12)) window(.ref_clk(ref_clk),.rst(rst),.start(start),.stop(stop),.requested_ticks(ticks),.stop_reason(stop_reason),
    .window_open(active),.done(done),.rejected(rejected),.elapsed_ticks(elapsed),.reason(reason));
  integer window_cases=0;
  task launch(input integer count);
    begin @(negedge ref_clk);ticks=count;start=1;@(negedge ref_clk);start=0;end
  endtask
  task normal(input integer count);
    integer observed;begin
      launch(count);observed=0;
      while(active)begin observed=observed+1;@(negedge ref_clk);end
      if(observed!=count || elapsed!=count || !done || reason || rejected)$fatal(1,"reference window duration %0d got %0d",count,observed);
      repeat(2)@(negedge ref_clk);if(done || elapsed!=count)$fatal(1,"window result not held");
      window_cases=window_cases+1;
    end
  endtask
  reg wr_clk=0,rd_clk=0,wr_clock_on=1,rd_clock_on=1;
  always #3 if(wr_clock_on)wr_clk=!wr_clk;
  always #5 if(rd_clock_on)rd_clk=!rd_clk;
  reg fifo_rst=1;reg [133:0] wr_data=0;reg wr_valid=0,rd_ready=0;wire wr_ready,rd_valid;
  wire [133:0] rd_data;wire [FIFO_ADDR:0] wr_level;
  etm_frame_async_fifo #(.ADDR_BITS(FIFO_ADDR)) fifo(.wr_clk(wr_clk),.wr_rst(fifo_rst),.wr_data(wr_data),.wr_valid(wr_valid),.wr_ready(wr_ready),.wr_level(wr_level),
    .rd_clk(rd_clk),.rd_rst(fifo_rst),.rd_data(rd_data),.rd_valid(rd_valid),.rd_ready(rd_ready));
  reg [133:0] expected[0:8191];integer pushed=0,popped=0,stalls=0;
  reg blocked=0;reg [133:0] held;
  always @(posedge wr_clk)if(!fifo_rst)begin
    if(wr_valid&&wr_ready)begin expected[pushed]=wr_data;pushed=pushed+1;end
    if(wr_valid&&!wr_ready)stalls=stalls+1;
    if(wr_level>DEPTH)$fatal(1,"occupancy outside capacity");
  end
  always @(posedge rd_clk)if(!fifo_rst)begin
    if(blocked && (!rd_valid || rd_data!==held))$fatal(1,"frame changed under backpressure");
    blocked=rd_valid&&!rd_ready;held=rd_data;
    if(rd_valid&&rd_ready)begin
      if(popped>=pushed || rd_data!==expected[popped])$fatal(1,"frame/EOF/length order at %0d",popped);
      popped=popped+1;
    end
  end else blocked=0;
  function [133:0] payload(input integer n);
    begin payload={(n%17==0),5'(n%16+1),32'(n),32'(~n),32'(n*13),32'(n*31)};end
  endfunction
  task send(input integer n);
    begin
      @(negedge wr_clk);wr_data=payload(n);wr_valid=1;
      @(posedge wr_clk);while(!wr_ready)@(posedge wr_clk);
      @(negedge wr_clk);wr_valid=0;
    end
  endtask
  reg consumer_random=0;integer read_cycle=0;
  always @(negedge rd_clk)if(consumer_random)begin read_cycle=read_cycle+1;rd_ready=(read_cycle%11!=0 && read_cycle%11!=1 && read_cycle%11!=2);end
  initial begin
    repeat(3)@(negedge ref_clk);rst=0;
    normal(1);normal(2);normal(3);normal(7);normal(255);normal(256);normal(4094);normal(4095);
    launch(0);if(active || !rejected || reason!=3)$fatal(1,"zero window accepted");window_cases=window_cases+1;
    launch(20);ticks=2;repeat(5)@(negedge ref_clk);start=1;@(negedge ref_clk);start=0;
    while(active)@(negedge ref_clk);if(elapsed!=20 || !rejected || reason)$fatal(1,"busy start/config changed window");window_cases=window_cases+1;
    launch(50);repeat(7)@(negedge ref_clk);stop=1;stop_reason=2;@(negedge ref_clk);stop=0;
    if(active || elapsed!=8 || reason!=2 || !done)$fatal(1,"bounded stop");window_cases=window_cases+1;
    normal(9);
    @(negedge wr_clk);fifo_rst=0;
    // Full capacity counts the output register as an occupied memory entry.
    rd_ready=0;
    for(integer n=0;n<DEPTH;n=n+1)send(n);
    repeat(8)@(negedge wr_clk);if(wr_ready || wr_level!=DEPTH)$fatal(1,"full FIFO not bounded");
    consumer_random=1;
    for(integer n=DEPTH;n<FRAMES;n=n+1)send(n);
    while(popped<pushed)@(negedge rd_clk);
    consumer_random=0;rd_ready=0;
    // Stop read clock, fill safely, then drain while write clock is stopped.
    @(negedge rd_clk);rd_clock_on=0;
    for(integer n=FRAMES;n<FRAMES+DEPTH;n=n+1)send(n);
    repeat(8)@(negedge wr_clk);if(wr_ready)$fatal(1,"read-clock absence overwrote frames");
    @(negedge wr_clk);wr_clock_on=0;rd_clock_on=1;rd_ready=1;
    while(popped<pushed)@(negedge rd_clk);
    repeat(12)@(negedge rd_clk);if(rd_valid)$fatal(1,"stopped source fabricated a frame");
    wr_clock_on=1;rd_ready=0;
    // New capture epoch discards an intentionally unconsumed old frame.
    send(2000);repeat(6)@(negedge rd_clk);
    fifo_rst=1;wr_valid=0;repeat(5)@(negedge rd_clk);pushed=0;popped=0;fifo_rst=0;rd_ready=1;
    for(integer n=3000;n<3020;n=n+1)send(n);
    while(popped<pushed)@(negedge rd_clk);
    repeat(8)@(negedge rd_clk);if(rd_valid)$fatal(1,"capture reset retained stale data");
    $display("PASS reference windows=%0d; async frames=%0d depth=%0d with EOF/length metadata, backpressure, stopped clocks and capture reset",window_cases,FRAMES+DEPTH+20,DEPTH);
    $finish;
  end
  initial begin #5000000;$fatal(1,"primitive test timeout");end
endmodule
