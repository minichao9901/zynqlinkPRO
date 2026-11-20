`timescale 1ns/1ps
// Eight independent pad samples per 100 Mbit/s Manchester information bit.
// Select centered samples of each half. Reacquire at every TPIU start bit.
module selectio_manchester_fast (
    input wire clk,reset,enable,phase,input wire [7:0] samples,
    output reg valid,output reg [7:0] data,output reg framing_error
);
    reg [7:0] prior;
    reg preceding,locked;
    reg [2:0] start_slot;
    reg [6:0] bits_in;
    reg [63:0] frame,drain;
    reg [3:0] drain_bytes;
    wire [15:0] window={samples,prior};
    wire [7:0] rising=prior & ~{prior[6:0],preceding};
    wire [2:0] first=rising[0]?0:rising[1]?1:rising[2]?2:rising[3]?3:
                     rising[4]?4:rising[5]?5:rising[6]?6:7;
    wire [3:0] center=phase ? 4'd2 : 4'd1;
    wire [3:0] offset={1'b0,(locked ? start_slot : first)}+center;
    wire high_half=window[offset],low_half=window[offset+4'd4];
    // A slightly faster source can place the next start just before the
    // next quartet boundary. Consume it together with the current stop.
    wire early_next=locked && start_slot==0 && rising[7] &&
                    window[4'd7+center] && !window[4'd11+center];

    always @(posedge clk) begin
        preceding<=prior[7];prior<=samples;valid<=0;framing_error<=0;
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
                    if(early_next) begin locked<=1;start_slot<=7;bits_in<=0;end
                end else framing_error<=1;
            end
        end
    end
endmodule
