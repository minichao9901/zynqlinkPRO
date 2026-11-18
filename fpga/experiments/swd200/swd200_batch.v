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
    output reg write_result = 0,
    output reg [8:0] result_addr,
    output reg [31:0] result_word,
    output reg [9:0] completed = 0,
    output reg [3:0] error = 0,
    output reg failed = 0,
    output reg [15:0] wait_retries = 0,
    output reg done = 0,
    input wire [3:0] rx_slots,
    output wire [3:0] clk_slots, data_slots, release_slots
);
    localparam IDLE = 0, PREFILL = 1, TRANSFER = 2, COMPLETE = 3;
    localparam EMPTY = 0, FETCH_OP = 1, FETCH_DATA = 2, FETCH_STORE = 3;
    reg [1:0] state = IDLE, fetch = EMPTY;
    (* ASYNC_REG = "TRUE" *) reg [1:0] request_sync = 0;
    reg [8:0] fetch_index;
    reg [8:0] next_header, current_header;
    reg [32:0] next_word, current_word;
    reg next_last, current_last;
    reg next_valid = 0;
    reg [5:0] attempts;
    reg [9:0] active_count;
    reg [1:0] active_rate;
    reg [5:0] active_ack_sample, active_data_sample;
    reg [3:0] active_idle;
    wire link_done, parity_error;
    wire [2:0] ack;
    wire [31:0] link_data;
    wire good = current_header[8] || (ack == 3'b001 && !parity_error);
    wire retire = state == TRANSFER && link_done;
    wire retry = retire && !good && ack == 3'b010 && attempts != 6'd63;
    wire issue_next = next_valid && (state == PREFILL || (retire && good && !current_last));
    wire [8:0] issue_header = retry ? current_header : next_header;
    wire [32:0] issue_word = retry ? current_word : next_word;
    assign command_addr = {fetch_index, fetch != FETCH_OP};

    swd200_link link (
        .clk(clk), .reset(reset), .rate(active_rate),
        .ack_sample(active_ack_sample), .data_sample(active_data_sample),
        .idle_cycles(active_idle), .start(issue_next || retry), .enter_swd(issue_header[8]),
        .header(issue_header[7:0]), .write_packet(issue_word),
        .done(link_done), .ack(ack), .parity_error(parity_error), .read_data(link_data),
        .rx_slots(rx_slots), .clk_slots(clk_slots), .data_slots(data_slots), .release_slots(release_slots)
    );

    // Commit in the next word clock, in parallel with issuing the next
    // request. This keeps the PHY reset out of the BRAM write-enable cone.
    // A final write lands on the same edge that raises batch completion.
    always @(posedge clk) begin
        write_result <= !reset && retire && good;
        if (retire && good) begin
            result_addr <= completed[8:0];
            result_word <= link_data;
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            request_sync <= 0;
            state <= IDLE;
            fetch <= EMPTY;
            next_valid <= 0;
            done <= 0;
        end else begin
            request_sync <= {request_sync[0], run};
            case (fetch)
                FETCH_OP: fetch <= FETCH_DATA;
                FETCH_DATA: begin
                    // Frame the pending request while the wire is busy.
                    next_header <= {command_word[4], 1'b1, 1'b0,
                                    ^command_word[3:0], command_word[3:0], 1'b1};
                    next_last <= {1'b0, fetch_index} + 10'd1 == active_count;
                    fetch <= FETCH_STORE;
                end
                FETCH_STORE: begin
                    next_word <= {^command_word, command_word};
                    next_valid <= 1;
                    fetch <= EMPTY;
                end
                default: begin end
            endcase
            if (issue_next) begin
                current_header <= next_header;
                current_word <= next_word;
                current_last <= next_last;
                next_valid <= 0;
                attempts <= 0;
                if (!next_last) begin
                    fetch_index <= fetch_index + 1'b1;
                    fetch <= FETCH_OP;
                end
            end
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
                    fetch_index <= 0;
                    fetch <= FETCH_OP;
                    state <= PREFILL;
                end
                PREFILL: if (issue_next) state <= TRANSFER;
                TRANSFER: if (link_done) begin
                    if (good) begin
                        completed <= completed + 10'd1;
                        if (current_last) state <= COMPLETE;
                        else if (!issue_next) state <= PREFILL;
                    end else if (retry) begin
                        attempts <= attempts + 1'b1;
                        wait_retries <= wait_retries + 1'b1;
                    end else begin
                        error <= {parity_error, ack};
                        failed <= 1;
                        next_valid <= 0;
                        fetch <= EMPTY;
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
