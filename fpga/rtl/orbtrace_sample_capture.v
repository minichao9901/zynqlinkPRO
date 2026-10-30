`timescale 1ns/1ps
// Short, bounded 200 MHz logic-analyser burst for offline filter experiments.
// 24 five-bit samples per frame -> eight 15-bit records. At 200 MHz this needs
// 66.7 M records/s, below the 100 MHz system-side record port. 8128 frames
// leave room below the 64K-record BRAM limit even without any host draining.
// The ~0.975ms window can include M3's fixed 1024-trace-byte periodic sync.
module orbtrace_sample_capture #(parameter FRAMES=8128)(
  input wire clk,input wire rst,input wire [4:0] pads,
  output reg [127:0] frame,output reg frame_toggle,output reg started
);
  (* ASYNC_REG="TRUE" *) reg [4:0] pad_meta,pad_sync;
  reg [119:0] build;
  reg [4:0] sample_count;
  reg [12:0] frame_count;
  always @(posedge clk or posedge rst)
    if(rst)begin
      pad_meta<=0;pad_sync<=0;build<=0;sample_count<=0;frame_count<=0;
      frame<=0;frame_toggle<=0;started<=0;
    end else begin
      pad_meta<=pads;pad_sync<=pad_meta;
      if(frame_count<FRAMES)begin
        build<={build[114:0],pad_sync};
        if(sample_count==23)begin
          frame<={8'd0,build[114:0],pad_sync};frame_toggle<=!frame_toggle;
          sample_count<=0;frame_count<=frame_count+1'b1;started<=1;
        end else sample_count<=sample_count+1'b1;
      end
    end
endmodule
