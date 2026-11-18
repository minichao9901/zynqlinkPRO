`timescale 1ns/1ps
// One PS-owned command buffer crosses by request/completion handshake.
// A WAIT can be retried because the target declined the transfer. FAULT,
// malformed ACK and read parity errors terminate the batch at that command.
module swd200_batch (
    input wire clk, reset, run,
    input wire [9:0] count,
    input wire [1:0] rate,
    input wire [5:0] ack_sample, data_sample,
    input wire [3:0] idle_cycles,
    output wire [9:0] command_addr,
    input wire [31:0] command_word,
    output wire write_result,
    output wire [8:0] result_addr,
    output wire [31:0] result_word,
    output reg [9:0] completed = 0,
    output reg [3:0] error = 0,
    output reg failed = 0,
    output reg [15:0] wait_retries = 0,
    output reg done = 0,
    input wire [3:0] rx_slots,
    output wire [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, FETCH_OP = 1, FETCH_DATA = 2, ISSUE = 3, TRANSFER = 4, COMPLETE = 5;
    reg [2:0] state = IDLE;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync = 0;
    reg [4:0] opcode;
    reg [5:0] attempts;
    reg [9:0] active_count;
    reg [1:0] active_rate;
    reg [5:0] active_ack_sample, active_data_sample;
    reg [3:0] active_idle;
    wire enter_swd = opcode[4];
    wire link_done, parity_error;
    wire [2:0] ack;
    wire good = enter_swd || (ack == 3'b001 && !parity_error);
    assign command_addr = {completed[8:0], state != FETCH_OP};
    assign result_addr = completed[8:0];
    // The write enable depends only on word-domain registers. The host
    // invalidates results if the PHY loses its clock during a batch.
    assign write_result = state == TRANSFER && link_done && good;

    swd200_link link (
        .clk(clk), .reset(reset), .rate(active_rate),
        .ack_sample(active_ack_sample), .data_sample(active_data_sample),
        .idle_cycles(active_idle), .start(state == ISSUE), .enter_swd(enter_swd),
        .request(opcode[3:0]), .write_data(command_word),
        .busy(), .done(link_done), .ack(ack), .parity_error(parity_error), .read_data(result_word),
        .rx_slots(rx_slots), .clk_slots(clk_slots), .data_slots(data_slots), .release_slots(release_slots)
    );

    always @(posedge clk) begin
        if (reset) begin
            request_sync <= 0;
            state <= IDLE;
            done <= 0;
        end else begin
            request_sync <= {request_sync[0], run};
            case (state)
                IDLE: if (request_sync[1]) begin
                    // The AXI domain holds all descriptor fields stable
                    // until the synchronized completion has returned.
                    active_count <= count;
                    active_rate <= rate;
                    active_ack_sample <= ack_sample;
                    active_data_sample <= data_sample;
                    active_idle <= idle_cycles;
                    completed <= 0;
                    error <= 0;
                    failed <= 0;
                    wait_retries <= 0;
                    state <= FETCH_OP;
                end
                FETCH_OP: state <= FETCH_DATA;
                FETCH_DATA: begin
                    opcode <= command_word[4:0];
                    attempts <= 0;
                    state <= ISSUE;
                end
                ISSUE: state <= TRANSFER;
                TRANSFER: if (link_done) begin
                    if (good) begin
                        completed <= completed + 10'd1;
                        state <= completed + 10'd1 == active_count ? COMPLETE : FETCH_OP;
                    end else if (ack == 3'b010 && attempts != 6'd63) begin
                        attempts <= attempts + 1'b1;
                        wait_retries <= wait_retries + 1'b1;
                        state <= ISSUE;
                    end else begin
                        error <= {parity_error, ack};
                        failed <= 1;
                        state <= COMPLETE;
                    end
                end
                COMPLETE: begin
                    done <= request_sync[1];
                    if (!request_sync[1]) state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
