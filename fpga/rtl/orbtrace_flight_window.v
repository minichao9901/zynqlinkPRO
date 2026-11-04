`timescale 1ns/1ps
// Flight mode waits for a trigger then captures requested_ticks more cycles.
// These counters measure the physical window, not USB or decoder latency.
module orbtrace_flight_window(
  input wire ref_clk,rst,start,stop,flight,trigger,
  input wire [31:0] requested_ticks,input wire [1:0] stop_reason,
  output reg window_open,done,rejected,triggered,
  output reg [31:0] elapsed_ticks,elapsed_high,trigger_ticks,trigger_high,
  output reg [1:0] reason
);
  reg [31:0] remaining;
  reg flight_held;
  always @(posedge ref_clk or posedge rst)
    if(rst)begin
      window_open<=0;done<=0;rejected<=0;triggered<=0;flight_held<=0;
      elapsed_ticks<=0;elapsed_high<=0;trigger_ticks<=0;trigger_high<=0;remaining<=0;reason<=0;
    end else begin
      done<=0;
      if(start)begin
        if(window_open)rejected<=1;
        else if(requested_ticks==0 || stop)begin rejected<=1;done<=1;reason<=3;end
        else begin
          window_open<=1;done<=0;rejected<=0;triggered<=0;flight_held<=flight;
          elapsed_ticks<=0;elapsed_high<=0;trigger_ticks<=0;trigger_high<=0;
          remaining<=requested_ticks;reason<=0;
        end
      end
      if(window_open)begin
        elapsed_ticks<=elapsed_ticks+1'b1;
        if(elapsed_ticks==32'hffffffff)elapsed_high<=elapsed_high+1'b1;
        if(flight_held && trigger && !triggered)begin
          triggered<=1;trigger_ticks<=elapsed_ticks+1'b1;
          trigger_high<=elapsed_high+(elapsed_ticks==32'hffffffff);
        end
        if(!flight_held || triggered)remaining<=remaining-1'b1;
        if(stop || ((!flight_held || triggered) && remaining==1))begin
          window_open<=0;done<=1;reason<=stop ? (stop_reason==0 ? 2'd3 : stop_reason) : 2'd0;
        end
      end
    end
endmodule
