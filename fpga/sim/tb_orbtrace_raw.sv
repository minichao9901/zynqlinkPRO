`timescale 1ns/1ps
// Exercise raw DDR capture including full/half sync, block transitions and
// intermittent PS backpressure. The 16-byte boundaries are transport-only.
module tb_orbtrace_raw #(parameter BOARD=0, MODE=1, DATA_AFTER_EDGE=0);
  reg clk=0;always #5 clk=~clk;
  reg sample_clk=0;always #2.5 sample_clk=~sample_clk;
  reg tclk=0,rst=1,ready=1;
  reg [3:0] pins=0;
  wire fabric_clk;
  generate if(BOARD)begin
    BUFR #(.BUFR_DIVIDE("BYPASS"),.SIM_DEVICE("7SERIES")) b(.I(tclk),.CE(1'b1),.CLR(1'b0),.O(fabric_clk));
  end else assign fabric_clk=tclk;endgenerate
  wire [7:0] data;wire [6:0] channel;wire valid,synced,overflow;
  orbtrace_parallel #(.RAW_DIAGNOSTIC(MODE),.USE_IO_CLOCK(BOARD),.USE_INPUT_DELAY(BOARD)) dut(.trace_clk(fabric_clk),.trace_io_clk(tclk),.trace_pad_clk(tclk),.sample_clk(sample_clk),
    .trace_data(pins),.width(2'd3),.clk(clk),.rst(rst),.data(data),
    .channel(channel),.valid(valid),.ready(ready),.synced(synced),.overflow(overflow));
  reg [7:0] pattern[0:15];reg [7:0] received[0:4095];
  integer count=0,cycles=0,n,i,start,ok,found=0,shift=0;
  always @(posedge clk)begin
    cycles<=cycles+1;
    ready<=cycles%11!=0 && cycles%11!=1;
    if(valid && ready)begin
      if(channel!=2 || count>=4096)$fatal(1,"raw channel/count");
      received[count]=data;count=count+1;
    end
  end
  task sendbyte(input [7:0] v);
    begin
      // A 2 ns clock glitch must not produce a qualified oversample edge.
      if(MODE==2 && DATA_AFTER_EDGE)begin
        #17;tclk=1;#2;tclk=0;#63;tclk=1;
        #2;pins=v[3:0];#81;tclk=0;#2;pins=v[7:4];#81;
      end else if(MODE==2)begin
        pins=v[3:0];
        #17;tclk=1;#2;tclk=0;#63;tclk=1;
        #40;pins=v[7:4];#43;tclk=0;#30;
      end else begin pins=v[3:0];#90;tclk=1;#110;pins=v[7:4];#90;tclk=0;#110;end
    end
  endtask
  initial begin
    pattern[0]='hff;pattern[1]='hff;pattern[2]='hff;pattern[3]='h7f;
    pattern[4]='h05;pattern[5]='hab;pattern[6]='h10;pattern[7]='h11;
    pattern[8]='h12;pattern[9]='h13;pattern[10]='h07;pattern[11]='h91;
    pattern[12]='h20;pattern[13]='h21;pattern[14]='h22;pattern[15]='h23;
    if($value$plusargs("shift=%d",shift))begin end
    #(shift);repeat(4)sendbyte(0);rst=0;repeat(32)sendbyte(0);
    for(n=0;n<80;n=n+1)for(i=0;i<16;i=i+1)sendbyte(pattern[i]);
    repeat(32)sendbyte(0);repeat(100)@(posedge clk);
    if(overflow || count<1000)$fatal(1,"raw overflow/count %d %d",overflow,count);
    for(start=0;start<count-256;start=start+1)begin
      ok=1;
      for(i=0;i<256;i=i+1)if(received[start+i]!==pattern[i%16])ok=0;
      if(ok)found=1;
    end
    if(!found)$fatal(1,"raw DDR payload differs or sync bytes were stripped");
    $display("PASS raw DDR bytes/sync/transport blocks/backpressure: %0d bytes",count);
    $finish;
  end
  initial begin #10000000;$fatal(1,"timeout");end
endmodule
