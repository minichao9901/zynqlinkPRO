`timescale 1ns/1ps
// Verilog adaptation of ORBTrace Unmangle/TrackStream/StripChannelZero.
// BSD-3-Clause; upstream and license: third_party/orbtrace/.
// Byte zero is frame[127:120]. The final byte restores the LSBs of
// the even bytes. An ID with its restored LSB set switches AFTER the
// following data byte; otherwise it switches immediately.
module orbtrace_tpiu_demux (
    input wire clk,input wire rst,
    input wire [127:0] frame,input wire frame_valid,output wire frame_ready,
    output wire [7:0] data,output wire [6:0] channel,
    output wire valid,input wire ready
);
    reg [127:0] buf_frame;
    reg [3:0] index;
    reg active;
    reg [6:0] current_channel,next_channel;
    reg pending;
    wire [7:0] raw_byte = buf_frame >> ((15-index)*8);
    wire id = !index[0] && raw_byte[0];
    wire [7:0] restored = index[0] ? raw_byte : {raw_byte[7:1],buf_frame[index>>1]};
    assign data = restored;
    assign channel = current_channel;
    assign valid = active && !id && current_channel!=0;
    assign frame_ready = !active;
    wire consume = active && (!valid || ready);
    always @(posedge clk or posedge rst)
      if(rst)begin
        buf_frame<=0;index<=0;active<=0;current_channel<=0;next_channel<=0;pending<=0;
      end else begin
        if(frame_valid && frame_ready)begin buf_frame<=frame;index<=0;active<=1;end
        if(consume)begin
          if(id)begin
            if(restored[0])begin next_channel<=restored[7:1];pending<=1;end
            else begin current_channel<=restored[7:1];pending<=0;end
          end else if(pending)begin current_channel<=next_channel;pending<=0;end
          if(index==14)active<=0;else index<=index+1'b1;
        end
      end
endmodule
