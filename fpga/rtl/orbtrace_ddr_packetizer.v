`timescale 1ns/1ps
// Bounded framed-TPIU stream frontend.
// Little-endian 0..16 byte frames -> AXIS64. Hold the last beat until a
// following beat or EOF is known; stop never fabricates an empty DMA beat.
// stream_bytes counts AXIS handshakes, NOT committed DDR writes.
module orbtrace_ddr_packetizer(
  input wire clk,input wire rst,
  input wire start,input wire [31:0] byte_limit,
  output reg busy,output reg done,output reg empty,
  output reg command_rejected,output reg protocol_error,output reg limit_reached,
  input wire [127:0] frame_data,input wire [4:0] frame_bytes,input wire frame_last,
  input wire frame_valid,output wire frame_ready,
  output wire [63:0] m_axis_tdata,output wire [7:0] m_axis_tkeep,
  output wire m_axis_tlast,output wire m_axis_tvalid,input wire m_axis_tready,
  output reg [31:0] input_bytes,output reg [31:0] stream_bytes
);
  reg [31:0] limit;
  reg [127:0] buffer;
  reg [4:0] remaining;
  reg buffer_last;
  reg [63:0] held_data;
  reg [7:0] held_keep;
  reg held_valid,held_last;
  wire next_beat=remaining!=0;
  assign frame_ready=busy && !protocol_error && remaining==0 && !held_last;
  assign m_axis_tdata=held_data;
  assign m_axis_tkeep=held_keep;
  assign m_axis_tlast=held_last;
  assign m_axis_tvalid=busy && held_valid && (held_last || next_beat);
  wire output_fire=m_axis_tvalid && m_axis_tready;
  wire load_beat=busy && next_beat && (!held_valid || output_fire);
  wire [31:0] room=limit-input_bytes;
  wire [4:0] accepted=room<frame_bytes ? room[4:0] : frame_bytes;
  function [7:0] keep_mask(input [4:0] length);
    begin keep_mask=length>=8 ? 8'hff : (8'h1<<length)-1'b1;end
  endfunction
  function [3:0] count_keep(input [7:0] keep);
    integer i;begin count_keep=0;for(i=0;i<8;i=i+1)count_keep=count_keep+keep[i];end
  endfunction
  always @(posedge clk)
    if(rst)begin
      busy<=0;done<=0;empty<=0;command_rejected<=0;protocol_error<=0;limit_reached<=0;
      limit<=0;buffer<=0;remaining<=0;buffer_last<=0;
      held_data<=0;held_keep<=0;held_valid<=0;held_last<=0;input_bytes<=0;stream_bytes<=0;
    end else begin
      done<=0;
      if(start)begin
        if(busy || protocol_error || byte_limit==0)command_rejected<=1;
        else begin
          busy<=1;empty<=0;command_rejected<=0;limit_reached<=0;
          limit<=byte_limit;remaining<=0;held_valid<=0;held_last<=0;input_bytes<=0;stream_bytes<=0;
        end
      end
      if(frame_valid && frame_ready)begin
        if(frame_bytes>16 || (frame_bytes==0 && !frame_last))begin
          protocol_error<=1;busy<=0;held_valid<=0;
          // A malformed internal frame requires the controller to reset DMA;
          // do not claim a committed packet or silently manufacture TLAST.
        end else if(frame_bytes==0)begin
          if(held_valid)held_last<=1;
          else begin empty<=1;done<=1;busy<=0;end
        end else begin
          buffer<=frame_data;remaining<=accepted;
          buffer_last<=frame_last || accepted==room;
          input_bytes<=input_bytes+accepted;
          if(accepted==room)limit_reached<=1;
        end
      end
      if(load_beat)begin
        held_data<=buffer[63:0];held_keep<=keep_mask(remaining);held_valid<=1;
        held_last<=buffer_last && remaining<=8;
        buffer<=buffer>>64;remaining<=remaining>8 ? remaining-8 : 0;
      end else if(output_fire)begin
        held_valid<=0;
        if(held_last)begin busy<=0;done<=1;end
      end
      if(output_fire)stream_bytes<=stream_bytes+count_keep(held_keep);
    end
endmodule
