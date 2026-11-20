`timescale 1ns/1ps
// One quartet advances the sample clock by four slots. Period in units
// of 1/256 slot gives accurate standard UART baud rates at 400 MS/s.
module selectio_uart_rx(
    input wire clk, reset, enable, input wire [3:0] samples,
    input wire [31:0] period_q8,
    output reg valid, output reg [7:0] data, output reg framing_error
);
    localparam IDLE=0, START=1, DATA=2, STOP=3;
    reg [1:0] state;
    reg previous;
    reg [31:0] remaining;
    reg [2:0] index;
    reg [7:0] shift;
    wire [3:0] falling={samples[2:0],previous} & ~samples;
    wire due=remaining<1024;
    wire [1:0] sample_slot=remaining[9:8];
    wire sampled=samples[sample_slot];
    // Back-to-back 100 Mbaud frames can put the next falling edge in the
    // same quartet as the preceding stop-bit center.
    wire [3:0] later=4'b1110 << sample_slot;
    wire [3:0] candidates=state==IDLE ? falling :
        (state==STOP && due && sampled ? falling & later : 4'b0);
    wire [1:0] first=candidates[0]?0:candidates[1]?1:candidates[2]?2:3;
    wire [31:0] start_center=(period_q8>>1)+{22'b0,first,8'b0};
    always @(posedge clk) begin
        previous<=samples[3];
        valid<=0;framing_error<=0;
        if(reset || !enable) begin
            state<=IDLE;remaining<=0;index<=0;
        end else begin
            if (state!=IDLE) begin
                if (!due) remaining<=remaining-1024;
                else begin
                    remaining<=remaining+period_q8-1024;
                    case(state)
                        START: state<=sampled ? IDLE : DATA;
                        DATA: begin
                            shift[index]<=sampled;
                            index<=index+1'b1;
                            if(index==7) state<=STOP;
                        end
                        STOP: begin
                            data<=shift;valid<=sampled;framing_error<=!sampled;state<=IDLE;
                        end
                        default: state<=IDLE;
                    endcase
                end
            end
            if (|candidates) begin
                index<=0;
                if(start_center>=1024) begin
                    remaining<=start_center-1024;state<=START;
                end else if(!samples[start_center[9:8]]) begin
                    remaining<=start_center+period_q8-1024;state<=DATA;
                end else state<=IDLE;
            end
        end
    end
endmodule
