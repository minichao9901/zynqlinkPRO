`timescale 1ns/1ps
// At four samples per information bit a three-slot pulse can be either a
// shortened full bit or a stretched half bit. Lock to the start-bit phase
// instead. A TPIU frame lasts at most 64 data bits and resynchronizes at
// every start. Publish only complete frames with a valid two-low-symbol stop.
module selectio_manchester_fast(input wire clk,reset,enable,phase,
                                input wire [3:0] samples,output reg valid,
                                output reg [7:0] data,output reg framing_error);
    reg [3:0] prior;
    reg preceding,locked;
    reg [1:0] start_slot;
    reg [6:0] bits_in;
    reg [63:0] frame,drain;
    reg [3:0] drain_bytes;
    wire [7:0] window={samples,prior};
    wire [3:0] rising=prior & ~{prior[2:0],preceding};
    wire [1:0] first=rising[0]?0:rising[1]?1:rising[2]?2:3;
    wire [2:0] offset={1'b0,(locked ? start_slot : first)}+phase;
    wire high_half=window[offset], low_half=window[offset+3'd2];
    always @(posedge clk) begin
        preceding<=prior[3];prior<=samples;valid<=0;framing_error<=0;
        if(reset || !enable) begin locked<=0;bits_in<=0;drain_bytes<=0;end
        else begin
            if(drain_bytes!=0) begin
                data<=drain[7:0];drain<={8'b0,drain[63:8]};drain_bytes<=drain_bytes-1'b1;valid<=1;
            end
            if(!locked) begin
                if((|rising) && high_half && !low_half) begin locked<=1;start_slot<=first;bits_in<=0;end
            end else if(high_half!=low_half && bits_in<64) begin
                frame<={high_half,frame[63:1]};bits_in<=bits_in+1'b1;
            end else begin
                locked<=0;
                if(!high_half && !low_half && bits_in!=0 && bits_in[2:0]==0 && drain_bytes==0) begin
                    drain<=frame>>(7'd64-bits_in);drain_bytes<=bits_in[6:3];
                end else framing_error<=1;
            end
        end
    end
endmodule
