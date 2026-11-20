`timescale 1ns/1ps
// Four chronological UART samples per word, LSB first, 8N1. Period is
// measured in 1/256 of a 2.5 ns pad slot. At most one bit boundary per word.
module selectio_uart_tx(
    input wire clk, reset, start, input wire [12:0] count,
    input wire [31:0] period_q8, input wire [31:0] tx_word,
    output wire [9:0] tx_addr, output reg [3:0] slots,
    output reg busy, done
);
    localparam IDLE=0, FETCH=1, SEND=2, DRAIN=3;
    reg [1:0] state;
    reg [12:0] byte_index,length;
    reg [3:0] bit_index;
    reg [31:0] remaining;
    reg [7:0] character;
    reg level;
    reg [2:0] drain;
    wire due=remaining<1024;
    wire [1:0] boundary=remaining[9:8];
    wire next_level=bit_index==0 ? 1'b0 : bit_index==9 ? 1'b1 : character[bit_index-1'b1];
    // Fetch the next byte during the current character's stop-bit interval.
    wire [12:0] lookahead=byte_index+1'b1;
    assign tx_addr=state==SEND ? lookahead[11:2] : 0;
    always @* begin
        slots={4{level}};
        if(state==SEND && due)
            for(integer i=0;i<4;i=i+1) if(i>=boundary) slots[i]=next_level;
    end
    always @(posedge clk) begin
        done<=0;
        if(reset) begin state<=IDLE;busy<=0;level<=1;byte_index<=0;end
        else case(state)
            IDLE: if(start && count!=0 && count<=4096) begin
                length<=count;byte_index<=0;busy<=1;state<=FETCH;
            end
            FETCH: begin
                character<=tx_word[7:0];bit_index<=0;remaining<=0;state<=SEND;
            end
            SEND: if(!due) remaining<=remaining-1024;
            else begin
                remaining<=remaining+period_q8-1024;
                level<=next_level;
                if(bit_index==9) begin
                    if(lookahead==length) begin state<=DRAIN;drain<=4;end
                    else begin
                        character<=tx_word[lookahead[1:0]*8+:8];
                        byte_index<=lookahead;bit_index<=0;
                    end
                end else bit_index<=bit_index+1'b1;
            end
            DRAIN: if(remaining>=1024) remaining<=remaining-1024;
            else if(drain!=0) drain<=drain-1'b1;
            else begin done<=1;busy<=0;state<=IDLE;end
        endcase
    end
endmodule
