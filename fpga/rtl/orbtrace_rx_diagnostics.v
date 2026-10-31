`timescale 1ns/1ps
// Capture-scoped diagnostics survive receiver stop/reset. Source counters are
// registered Gray codes, synchronized to clk; read after stop/CDC settling.
module orbtrace_rx_diagnostics(
  input wire source_clk,input wire capture_reset,input wire diagnostic_reset,
  input wire frame_drop,input wire parser_error,input wire sync_acquire,
  input wire [3:0] frame_level,
  input wire clk,input wire rst,
  output wire [1:0] flags,
  output reg [31:0] dropped_frames,parser_errors,sync_acquisitions,frame_highwater
);
  reg [1:0] seen;
  reg [31:0] drops,errors,syncs,highwater;
  reg [31:0] drops_gray,errors_gray,syncs_gray,highwater_gray;
  wire [31:0] next_drops=drops+1'b1,next_errors=errors+1'b1,next_syncs=syncs+1'b1;
  always @(posedge source_clk or posedge diagnostic_reset)
    if(diagnostic_reset)begin
      seen<=0;drops<=0;errors<=0;syncs<=0;highwater<=0;
      drops_gray<=0;errors_gray<=0;syncs_gray<=0;highwater_gray<=0;
    end else if(!capture_reset)begin
      if(frame_drop)begin seen[0]<=1;drops<=next_drops;drops_gray<=(next_drops>>1)^next_drops;end
      if(parser_error)begin seen[1]<=1;errors<=next_errors;errors_gray<=(next_errors>>1)^next_errors;end
      if(sync_acquire)begin syncs<=next_syncs;syncs_gray<=(next_syncs>>1)^next_syncs;end
      if(frame_level>highwater)begin highwater<=frame_level;highwater_gray<=(frame_level>>1)^frame_level;end
    end
  (* ASYNC_REG="TRUE" *) reg [1:0] seen_meta,seen_sync;
  (* ASYNC_REG="TRUE" *) reg [31:0] drops_meta,drops_sync,errors_meta,errors_sync;
  (* ASYNC_REG="TRUE" *) reg [31:0] syncs_meta,syncs_sync,highwater_meta,highwater_sync;
  always @(posedge clk or posedge rst)
    if(rst)begin
      seen_meta<=0;seen_sync<=0;drops_meta<=0;drops_sync<=0;errors_meta<=0;errors_sync<=0;
      syncs_meta<=0;syncs_sync<=0;highwater_meta<=0;highwater_sync<=0;
      dropped_frames<=0;parser_errors<=0;sync_acquisitions<=0;frame_highwater<=0;
    end else begin
      seen_meta<=seen;seen_sync<=seen_meta;
      drops_meta<=drops_gray;drops_sync<=drops_meta;errors_meta<=errors_gray;errors_sync<=errors_meta;
      syncs_meta<=syncs_gray;syncs_sync<=syncs_meta;highwater_meta<=highwater_gray;highwater_sync<=highwater_meta;
      dropped_frames<=binary(drops_sync);parser_errors<=binary(errors_sync);
      sync_acquisitions<=binary(syncs_sync);frame_highwater<=binary(highwater_sync);
    end
  function [31:0] binary(input [31:0] gray);
    integer i;begin binary[31]=gray[31];for(i=30;i>=0;i=i-1)binary[i]=binary[i+1]^gray[i];end
  endfunction
  assign flags=seen_sync;
endmodule
