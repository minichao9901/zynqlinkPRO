`timescale 1ns/1ps
// Replay real captured physical TPIU bytes into the existing DDR frontend.
// Input files and results are supplied externally; no target RTL is bundled.
module tb_orbtrace_replay #(parameter BOARD=0);
  reg clk=0;always #5 clk=~clk;
  reg tclk=0,rst=1;
  reg [3:0] pins=0;
  wire fabric_clk;
  generate if(BOARD)begin
    BUFR #(.BUFR_DIVIDE("BYPASS"),.SIM_DEVICE("7SERIES")) b(.I(tclk),.CE(1'b1),.CLR(1'b0),.O(fabric_clk));
  end else assign fabric_clk=tclk;endgenerate
  wire [7:0] data;wire [6:0] channel;wire valid,synced,overflow;
  orbtrace_parallel #(.USE_IO_CLOCK(BOARD),.USE_INPUT_DELAY(BOARD)) dut(
    .trace_clk(fabric_clk),.trace_io_clk(tclk),.trace_data(pins),.width(2'd3),
    .clk(clk),.rst(rst),.data(data),.channel(channel),.valid(valid),.ready(1'b1),.synced(synced),.overflow(overflow));
  reg [2047:0] source_name,sink_name;
  integer source,sink,c,bytes=0,records=0;
  always @(posedge clk)if(valid)begin $fwrite(sink,"%02x %02x\n",channel,data);records=records+1;end
  task sendbyte(input [7:0] v);
    begin pins=v[3:0];#90;tclk=1;#110;pins=v[7:4];#90;tclk=0;#110;end
  endtask
  initial begin
    if(!$value$plusargs("source=%s",source_name) || !$value$plusargs("sink=%s",sink_name))$fatal(1,"missing file paths");
    source=$fopen(source_name,"rb");sink=$fopen(sink_name,"w");
    if(!source || !sink)$fatal(1,"file open failed");
    repeat(4)sendbyte(0);rst=0;repeat(32)sendbyte(0);
    c=$fgetc(source);
    while(c!=-1)begin sendbyte(c[7:0]);bytes=bytes+1;c=$fgetc(source);end
    repeat(40)begin sendbyte('hff);sendbyte('h7f);end
    repeat(100)@(posedge clk);
    if(overflow)$fatal(1,"replay overflow");
    $display("PASS physical TPIU replay BOARD=%0d bytes=%0d records=%0d synced=%0d",BOARD,bytes,records,synced);
    $fclose(source);$fclose(sink);$finish;
  end
endmodule
