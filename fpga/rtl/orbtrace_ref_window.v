`timescale 1ns/1ps
// Reference-clock window primitive used by the framed DDR capture owner.
// Commands/configuration must already belong to ref_clk. The owner must CDC
// handshake commands, freeze configuration, and drain frames/AXI after done.
// done means window closed, never DDR completion or successful ETM decoding.
module orbtrace_ref_window #(parameter WIDTH=32)(
  input wire ref_clk,input wire rst,input wire start,input wire stop,
  input wire [WIDTH-1:0] requested_ticks,input wire [1:0] stop_reason,
  output reg window_open,output reg done,output reg rejected,
  output reg [WIDTH-1:0] elapsed_ticks,output reg [1:0] reason
);
  reg [WIDTH-1:0] last_tick;
  wire [WIDTH-1:0] next_ticks=elapsed_ticks+1'b1;
  always @(posedge ref_clk or posedge rst)
    if(rst)begin window_open<=0;done<=0;rejected<=0;elapsed_ticks<=0;last_tick<=0;reason<=0;end
    else begin
      done<=0;
      if(start)begin
        if(window_open)rejected<=1;
        else if(requested_ticks==0 || stop)begin
          rejected<=1;done<=1;elapsed_ticks<=0;reason<=3;
        end else begin
          window_open<=1;rejected<=0;elapsed_ticks<=0;last_tick<=requested_ticks-1'b1;reason<=0;
        end
      end
      if(window_open)begin
        elapsed_ticks<=next_ticks;
        if(stop || elapsed_ticks==last_tick)begin
          window_open<=0;done<=1;
          reason<=stop ? (stop_reason==0 ? 2'd3 : stop_reason) : 2'd0;
        end
      end
    end
endmodule
