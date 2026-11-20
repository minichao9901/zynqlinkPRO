`timescale 1ns/1ps
// The AXI side owns the TX/RX buffers before and after a scan.
// Addresses and waveforms remain stable until the scan is done.
module jtag200_wave (
    input wire clk, reset, run, input wire [1:0] park,
    output reg done = 0,
    output reg [8:0] tx_addr = 0,
    output reg [8:0] rx_addr = 0,
    output wire rx_write,
    input wire [24:0] tx_word,
    output wire [23:0] lane_word
);
    localparam IDLE = 0, FETCH = 1, PLAY = 2, DRAIN = 3, FINISHED = 4;
    reg [2:0] state = IDLE;
    (* ASYNC_REG = "TRUE" *) reg [1:0] run_sync = 0;
    reg [2:0] drain = 0;
    wire [23:0] idle_word = {{8{park[1]}},{8{park[0]}},8'd0};  // TDI/TMS high, TCK low

    assign lane_word = state == PLAY ? tx_word[23:0] : idle_word;
    assign rx_write = state == PLAY;

    always @(posedge clk) begin
        if (reset) begin
            run_sync <= 0;
            state <= IDLE;
            done <= 0;
            tx_addr <= 0;
            rx_addr <= 0;
            drain <= 0;
        end else begin
            run_sync <= {run_sync[0], run};
            case (state)
                IDLE: if (run_sync[1]) begin
                    tx_addr <= 0;
                    rx_addr <= 0;
                    state <= FETCH;
                end
                FETCH: begin
                    tx_addr <= 1;
                    state <= PLAY;
                end
                PLAY: begin
                    if (tx_word[24] || (&rx_addr)) begin
                        drain <= 5;
                        state <= DRAIN;
                    end else begin
                        tx_addr <= tx_addr + 1'b1;
                        rx_addr <= rx_addr + 1'b1;
                    end
                end
                DRAIN: if (drain == 0) begin
                    done <= 1;
                    state <= FINISHED;
                end else drain <= drain - 1'b1;
                FINISHED: if (!run_sync[1]) begin
                    done <= 0;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
