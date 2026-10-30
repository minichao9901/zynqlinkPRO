`timescale 1ns/1ps
// Replay every 5ns sample from a real five-line capture, preserving glitches.
module tb_orbtrace_signal_replay #(parameter MODE=4);
  reg clk=0;always #5 clk=~clk;
  reg sample_clk=0;always #2.5 sample_clk=~sample_clk;
  reg rst=1;reg [4:0] pads=0;
  wire [7:0] data;wire [6:0] channel;wire valid,synced,overflow;
  orbtrace_parallel #(.RAW_DIAGNOSTIC(MODE)) dut(.trace_clk(pads[4]),.trace_io_clk(pads[4]),
    .trace_pad_clk(pads[4]),.sample_clk(sample_clk),.trace_data(pads[3:0]),.width(2'd3),
    .clk(clk),.rst(rst),.data(data),.channel(channel),.valid(valid),.ready(1'b1),.synced(synced),.overflow(overflow));
  reg [2047:0] source_name,sink_name;
  integer source,sink,code,value,samples=0,records=0;
  always @(posedge clk)if(valid)begin $fwrite(sink,"%02x %02x\n",channel,data);records=records+1;end
  initial begin
    if(!$value$plusargs("source=%s",source_name) || !$value$plusargs("sink=%s",sink_name))$fatal(1,"missing paths");
    source=$fopen(source_name,"r");sink=$fopen(sink_name,"w");
    if(!source || !sink)$fatal(1,"file open failed");
    repeat(10)@(negedge sample_clk);rst=0;
    repeat(8)@(negedge sample_clk);
    while(!$feof(source))begin
      code=$fscanf(source,"%h\n",value);
      if(code==1)begin pads=value[4:0];samples=samples+1;@(negedge sample_clk);end
    end
    repeat(2000)@(posedge clk);
    $display("REPLAY mode=%0d samples=%0d records=%0d synced=%0d loss=%0d",MODE,samples,records,synced,overflow);
    $fclose(source);$fclose(sink);$finish;
  end
endmodule
