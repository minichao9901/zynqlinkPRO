`timescale 1ns/1ps
module tb_orbtrace_samples;
  reg clk=0;always #5 clk=~clk;
  reg sample_clk=0;always #2.5 sample_clk=~sample_clk;
  reg rst=1,ready=1;
  reg [4:0] pads=0;
  wire [7:0] data;wire [6:0] channel;wire valid,synced,overflow;
  orbtrace_parallel #(.RAW_DIAGNOSTIC(3)) dut(.trace_clk(pads[4]),.trace_io_clk(pads[4]),
    .trace_pad_clk(pads[4]),.sample_clk(sample_clk),.trace_data(pads[3:0]),.width(2'd3),
    .clk(clk),.rst(rst),.data(data),.channel(channel),.valid(valid),.ready(ready),.synced(synced),.overflow(overflow));
  integer records=0,cycles=0,i;
  reg [14:0] record;
  reg [4:0] value,previous;
  always @(negedge sample_clk)if(!rst)pads<=pads+1'b1;
  always @(posedge clk)begin
    cycles<=cycles+1;ready<=cycles%17!=0;
    if(valid&&ready)begin
      record={channel,data};
      for(i=2;i>=0;i=i-1)begin
        value=(record>>(5*i))&31;
        if(records>4 && value!==((previous+1)&31))$fatal(1,"sample dropped/reordered at record %0d",records);
        previous=value;
      end
      records=records+1;
    end
  end
  initial begin
    repeat(10)@(negedge sample_clk);rst=0;
    #1100000;
    if(records!=65024 || overflow || !synced)$fatal(1,"burst count/loss/sync: %0d %0d %0d",records,overflow,synced);
    #10000;
    if(records!=65024)$fatal(1,"burst was not bounded");
    $display("PASS raw sample burst: %0d records, 195072 samples, no loss, bounded",records);$finish;
  end
endmodule
