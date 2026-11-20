`timescale 1ns/1ps
// SPI master. Four pad samples per SCK at 100 MHz. The BRAM read port
// registers tx_word one cycle after tx_addr, in little-endian USB word order.
module selectio_spi (
    input wire clk, reset, start,
    input wire [1:0] mode,
    input wire [12:0] byte_count,
    input wire [5:0] sample_slot,
    output wire [9:0] tx_addr,
    input wire [31:0] tx_word,
    input wire [3:0] miso,
    output reg [3:0] sck, cs_n, mosi,
    output reg rx_valid,
    output reg [11:0] rx_addr,
    output reg [7:0] rx_byte,
    output reg busy, done
);
    localparam IDLE=0, SELECT=1, TRANSMIT=2, LAST_EDGE=3, DESELECT=4, COMPLETE=5, PARK=6;
    reg [2:0] state;
    reg [1:0] active_mode;
    reg [5:0] slot;
    reg [15:0] remaining, samples_left;
    reg [11:0] transmit_byte;
    reg [2:0] transmit_bit, receive_bit;
    reg [7:0] receive_shift;
    reg [11:0] receive_byte;
    reg [3:0] wait_words;
    reg previous_mosi, receiving;
    // Ask for the following word while emitting the last bit of this word.
    assign tx_addr = transmit_byte[11:2] +
        (state==TRANSMIT && transmit_byte[1:0]==3 && transmit_bit==7);
    wire bit_out = tx_word[{transmit_byte[1:0], ~transmit_bit}];
    wire cpol = active_mode[1], cpha = active_mode[0];

    always @* begin
        sck={4{cpol}};
        cs_n=4'hf;
        mosi={4{previous_mosi}};
        case (state)
            SELECT: begin cs_n=0; if (!cpha) mosi={4{bit_out}}; end
            TRANSMIT: begin
                cs_n=0;
                sck={{2{!cpol}}, {2{cpol}}};
                mosi=cpha ? {{2{bit_out}}, {2{previous_mosi}}} : {4{bit_out}};
            end
            LAST_EDGE: cs_n=0;
            default: ;
        endcase
    end

    always @(posedge clk) begin
        done<=0;
        rx_valid<=0;
        if (reset) begin
            state<=IDLE; busy<=0; receiving<=0; previous_mosi<=0;
            active_mode<=0; transmit_byte<=0; transmit_bit<=0;
        end else begin
            if (receiving) begin
                if (wait_words!=0) wait_words<=wait_words-1'b1;
                else begin
                    receive_shift<={receive_shift[6:0],miso[slot[1:0]]};
                    receive_bit<=receive_bit+1'b1;
                    if (receive_bit==7) begin
                        rx_valid<=1;
                        rx_byte<={receive_shift[6:0],miso[slot[1:0]]};
                        rx_addr<=receive_byte;
                        receive_byte<=receive_byte+1'b1;
                    end
                    samples_left<=samples_left-1'b1;
                    if (samples_left==1) receiving<=0;
                end
            end
            case (state)
                IDLE: if (start && byte_count!=0 && byte_count<=4096) begin
                    active_mode<=mode;
                    remaining<={byte_count,3'b0};
                    samples_left<={byte_count,3'b0};
                    transmit_byte<=0; transmit_bit<=0;
                    receive_byte<=0; receive_bit<=0;
                    slot<=sample_slot;
                    busy<=1;
                    state<=PARK;
                end
                PARK: state<=SELECT;
                SELECT: begin
                    receiving<=1;
                    wait_words<=slot[5:2];
                    state<=TRANSMIT;
                end
                TRANSMIT: begin
                    previous_mosi<=bit_out;
                    transmit_bit<=transmit_bit+1'b1;
                    if (transmit_bit==7) transmit_byte<=transmit_byte+1'b1;
                    remaining<=remaining-1'b1;
                    if (remaining==1) state<=LAST_EDGE;
                end
                LAST_EDGE: state<=DESELECT;
                DESELECT: if (!receiving && !rx_valid) state<=COMPLETE;
                COMPLETE: begin busy<=0; done<=1; state<=IDLE; end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
