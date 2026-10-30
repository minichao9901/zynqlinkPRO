`timescale 1ns/1ps
// Recover continuous 16-byte TPIU formatter frames. Sync is halfword aligned:
// FF 7F may interrupt a frame; FF FF FF 7F is only legal between frames.
// Acquire either byte phase from FSYNC; the clock/data relationship may put
// the oversampler on a byte boundary or half a nibble ahead.
module orbtrace_tpiu_stream (
    input wire clk,input wire rst,
    input wire [7:0] byte_in,input wire byte_toggle,
    output reg [127:0] frame,output reg frame_toggle,
    output reg synced,output reg malformed
);
    reg seen_toggle,have_previous;
    reg [7:0] previous_byte,first_byte;
    reg [31:0] sync_shift,direct_shift;
    reg [127:0] frame_build;
    reg [2:0] pair_count;
    reg have_first,full_sync_tail,shifted_phase;
    wire byte_event = byte_toggle != seen_toggle;
    wire [7:0] shifted_byte = {byte_in[3:0],previous_byte[7:4]};
    wire [7:0] stream_byte = shifted_phase ? shifted_byte : byte_in;
    wire [31:0] next_sync = {sync_shift[23:0],shifted_byte};
    wire [31:0] next_direct = {direct_shift[23:0],byte_in};
    wire [15:0] pair = {first_byte,stream_byte};

    always @(posedge clk or posedge rst)
      if(rst)begin
        seen_toggle<=0;have_previous<=0;previous_byte<=0;first_byte<=0;
        sync_shift<=0;direct_shift<=0;shifted_phase<=0;
        frame_build<=0;pair_count<=0;have_first<=0;full_sync_tail<=0;
        frame<=0;frame_toggle<=0;synced<=0;malformed<=0;
      end else if(byte_event)begin
        seen_toggle<=byte_toggle;
        previous_byte<=byte_in;
        if(!have_previous)have_previous<=1;
        else begin
          sync_shift<=next_sync;
          direct_shift<=next_direct;
          if(!synced)begin
            if(next_sync==32'hffff_ff7f || next_direct==32'hffff_ff7f)begin
              shifted_phase <= next_direct!=32'hffff_ff7f;
              synced<=1;have_first<=0;pair_count<=0;full_sync_tail<=0;
            end
          end else if(!have_first)begin
            first_byte<=stream_byte;have_first<=1;
          end else begin
            have_first<=0;
            if(full_sync_tail)begin
              full_sync_tail<=0;
              if(pair!=16'hff7f)begin
                malformed<=1;synced<=0;pair_count<=0;
              end
            end else if(pair==16'hff7f)begin
              // HSYNC occupies no formatter bytes, including inside a frame.
            end else if(pair==16'hffff)begin
              if(pair_count==0)full_sync_tail<=1;
              else begin
                // Never splice a partial frame across full sync. Retain a
                // sticky transport-loss indication even if later sync recovers.
                malformed<=1;synced<=0;pair_count<=0;
              end
            end else begin
              frame_build<={frame_build[111:0],pair};
              if(pair_count==7)begin
                frame<={frame_build[111:0],pair};
                frame_toggle<=!frame_toggle;
                pair_count<=0;
              end else pair_count<=pair_count+1'b1;
            end
          end
        end
      end
endmodule
