`timescale 1ns/1ps
// Recover 16-byte TPIU formatter frames from bytes produced by the
// synchronized ETM oversampler. The oversampler's first byte phase is a
// half-nibble ahead of the TPIU stream, so each emitted byte combines the
// previous raw byte's high nibble with the current raw byte's low nibble.
module orbtrace_tpiu_stream (
    input wire clk,input wire rst,
    input wire [7:0] byte_in,input wire byte_toggle,
    output reg [127:0] frame,output reg frame_toggle,
    output reg synced
);
    reg seen_toggle,have_previous;
    reg [7:0] previous_byte;
    reg [31:0] sync_shift;
    reg [127:0] frame_build;
    reg [4:0] frame_count;
    reg in_frame,prefix_done;
    reg [1:0] prefix_count;
    reg [31:0] prefix_bytes;
    wire byte_event = byte_toggle != seen_toggle;
    wire [7:0] stream_byte = {byte_in[3:0],previous_byte[7:4]};
    wire [31:0] next_sync = {sync_shift[23:0],stream_byte};
    wire [31:0] next_prefix = {prefix_bytes[23:0],stream_byte};

    always @(posedge clk or posedge rst)
      if(rst)begin
        seen_toggle<=0;have_previous<=0;previous_byte<=0;
        sync_shift<=0;frame_build<=0;frame_count<=0;in_frame<=0;
        prefix_done<=0;prefix_count<=0;prefix_bytes<=0;
        frame<=0;frame_toggle<=0;synced<=0;
      end else if(byte_event)begin
        seen_toggle<=byte_toggle;
        if(!have_previous)begin
          previous_byte<=byte_in;
          have_previous<=1;
        end else begin
          previous_byte<=byte_in;
          if(!synced)begin
            sync_shift<=next_sync;
            if(next_sync==32'hffff_ff7f)begin
              synced<=1;
              in_frame<=1;
              prefix_done<=0;
              prefix_count<=0;
              frame_count<=0;
              sync_shift<=0;
            end
          end else if(!in_frame)begin
            // Full sync is a frame boundary. Ignore idle and repeated FSYNC
            // words until a complete formatter frame starts.
            sync_shift<=next_sync;
            if(next_sync==32'hffff_ff7f)begin
              in_frame<=1;
              prefix_done<=0;
              prefix_count<=0;
              frame_count<=0;
              sync_shift<=0;
            end
          end else if(!prefix_done)begin
            // Hold four bytes so a repeated FSYNC immediately after a
            // boundary is discarded instead of becoming a fake frame.
            if(prefix_count!=3)begin
              prefix_bytes<=next_prefix;
              prefix_count<=prefix_count+1'b1;
            end else if(next_prefix==32'hffff_ff7f)begin
              prefix_bytes<=0;
              prefix_count<=0;
              frame_count<=0;
            end else begin
              frame_build<={96'd0,next_prefix};
              frame_count<=4;
              prefix_done<=1;
            end
          end else begin
            frame_build<={frame_build[119:0],stream_byte};
            if(frame_count==15)begin
              frame<={frame_build[119:0],stream_byte};
              frame_toggle<=!frame_toggle;
              frame_count<=0;
              in_frame<=0;
              prefix_done<=0;
              prefix_count<=0;
            end else frame_count<=frame_count+1'b1;
          end
        end
      end
endmodule
