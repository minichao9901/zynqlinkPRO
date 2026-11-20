`timescale 1ns/1ps
module swd200_regs (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET axi_aresetn" *)
    input wire axi_aclk, axi_aresetn,
    input wire [13:0] s_axi_awaddr,
    input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp = 0,
    output reg s_axi_bvalid = 0,
    input wire s_axi_bready,
    input wire [13:0] s_axi_araddr,
    input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata = 0,
    output reg [1:0] s_axi_rresp = 0,
    output reg s_axi_rvalid = 0,
    input wire s_axi_rready,
    output reg hold = 1,
    input wire delay_ready,
    output reg delay_load = 0,
    output reg [4:0] delay_value = 0,
    input wire word_clk, word_reset,
    input wire [3:0] rx_slots,
    output wire [3:0] clk_slots, data_slots, release_slots
);
    reg have_addr = 0, have_data = 0, reading_results = 0;
    reg [13:0] write_addr;
    reg [31:0] write_data;
    reg [3:0] write_strobes;
    reg run = 0, result_valid = 0;
    reg [9:0] count = 0;
    reg [6:0] mode = 0;
    wire [6:0] active_mode;
    wire begin_batch;
    // Layout: idle[17:14], data slot[13:8], ACK slot[7:2], rate[1:0].
    reg [17:0] timing = {4'd2, 6'd12, 6'd12, 2'd2};
    reg [31:0] summary = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] ready_sync = 0, done_sync = 0, delay_sync = 0;
    wire batch_done, batch_failed, write_result;
    wire [9:0] cmd_addr, completed;
    wire [8:0] result_addr;
    wire [31:0] result_word;
    wire [3:0] error;
    wire [15:0] wait_retries;
    reg [31:0] cmd_q, result_q;
    (* ram_style = "block" *) reg [31:0] commands [0:4095];
    (* ram_style = "block" *) reg [31:0] expected [0:255];
    (* ram_style = "block" *) reg [31:0] results [0:511];

    wire idle = !run && !done_sync[1];
    wire ready = ready_sync[1] && delay_sync[1] && !hold;
    wire aligned_write = write_strobes == 4'hf && write_addr[1:0] == 0;
    wire write_pending = have_addr && have_data && !s_axi_bvalid;
    wire write_command = write_pending && aligned_write && idle && write_addr[13:12] == 1;
    wire write_expected = write_pending && aligned_write && idle && write_addr[13:10] == 4'hc;
    wire read_pending = s_axi_arvalid && s_axi_arready;
    wire read_result = read_pending && s_axi_araddr[1:0] == 0 && result_valid &&
                       s_axi_araddr[13:11] == 3'b100 && {1'b0, s_axi_araddr[10:2]} < summary[9:0];
    assign s_axi_awready = !have_addr && !s_axi_bvalid;
    assign s_axi_wready = !have_data && !s_axi_bvalid;
    assign s_axi_arready = !reading_results && !s_axi_rvalid;

    reg [31:0] expected_q, actual_q;
    reg check_word = 0, mismatch = 0;
    reg [1:0] completed_pipe = 0;
    always @(posedge word_clk) begin
        cmd_q <= commands[{active_mode[1:0], cmd_addr}];
        if (write_result) results[result_addr] <= result_word;
        expected_q <= expected[result_addr[7:0] - 8'd2];
        actual_q <= result_word ^ {32{active_mode[2]}};
        check_word <= write_result && active_mode[3] && result_addr >= 2 && result_addr <= 257;
        completed_pipe <= {completed_pipe[0], batch_done};
        if (begin_batch || word_reset) mismatch <= 0;
        else if (check_word && actual_q != expected_q) mismatch <= 1;
    end
    always @(posedge axi_aclk) begin
        if (write_command) commands[{mode[1:0],write_addr[11:2]}] <= write_data;
        if (write_expected) expected[write_addr[9:2]] <= write_data;
        if (read_result) result_q <= results[s_axi_araddr[10:2]];
    end

    swd200_batch batch (
        .clk(word_clk), .reset(word_reset), .run(run), .count(count),
        .mode(mode), .active_mode(active_mode), .begin_batch(begin_batch),
        .rate(timing[1:0]), .ack_sample(timing[7:2]), .data_sample(timing[13:8]),
        .idle_cycles(timing[17:14]), .command_addr(cmd_addr), .command_word(cmd_q),
        .write_result(write_result), .result_addr(result_addr), .result_word(result_word),
        .completed(completed), .error(error), .failed(batch_failed),
        .wait_retries(wait_retries), .done(batch_done),
        .rx_slots(rx_slots), .clk_slots(clk_slots), .data_slots(data_slots), .release_slots(release_slots)
    );

    always @(posedge axi_aclk) begin
        if (!axi_aresetn) begin
            hold <= 1;
            delay_load <= 0;
            delay_value <= 0;
            timing <= {4'd2, 6'd12, 6'd12, 2'd2};
            count <= 0;
            mode <= 0;
            have_addr <= 0;
            have_data <= 0;
            s_axi_bvalid <= 0;
            s_axi_rvalid <= 0;
            reading_results <= 0;
            run <= 0;
            result_valid <= 0;
            ready_sync <= 0;
            done_sync <= 0;
            delay_sync <= 0;
            summary <= 0;
        end else begin
            ready_sync <= {ready_sync[0], !word_reset};
            done_sync <= {done_sync[0], completed_pipe[1]};
            delay_sync <= {delay_sync[0], delay_ready};
            delay_load <= 0;
            if (run && (!ready || done_sync[1])) begin
                summary <= ready ? {wait_retries, 1'b0, batch_failed || mismatch, error, completed}
                                 : 32'h0000c000;
                result_valid <= 1;
                run <= 0;
            end
            if (s_axi_awvalid && s_axi_awready) begin
                write_addr <= s_axi_awaddr;
                have_addr <= 1;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                write_data <= s_axi_wdata;
                write_strobes <= s_axi_wstrb;
                have_data <= 1;
            end
            if (s_axi_bready) s_axi_bvalid <= 0;
            if (write_pending) begin
                have_addr <= 0;
                have_data <= 0;
                s_axi_bvalid <= 1;
                s_axi_bresp <= 0;
                if (!aligned_write || !idle) s_axi_bresp <= 2'b10;
                else if (!write_command && !write_expected) begin
                    case (write_addr)
                        14'h08: hold <= write_data[0];
                        14'h0c: if (write_data[1:0] != 3)
                            timing <= write_data[17:0];
                        else s_axi_bresp <= 2'b10;
                        14'h10: if (ready && write_data > 0 && write_data <= 512 &&
                                    (!mode[3] || write_data == 259)) begin
                            count <= write_data[9:0];
                            run <= 1;
                            result_valid <= 0;
                        end else s_axi_bresp <= 2'b10;
                        14'h1c: if (write_data < 128 && write_data[1:0]!=3 &&
                                    (!write_data[3] || write_data[1:0]==1))
                            mode <= write_data[6:0];
                        else s_axi_bresp <= 2'b10;
                        14'h18: if (delay_sync[1] && write_data < 32) begin
                            delay_value <= write_data[4:0];
                            delay_load <= 1;
                        end else s_axi_bresp <= 2'b10;
                        default: s_axi_bresp <= 2'b10;
                    endcase
                end
            end

            if (s_axi_rready) s_axi_rvalid <= 0;
            if (read_pending) begin
                s_axi_rresp <= 0;
                if (read_result) begin
                    reading_results <= 1;
                end else begin
                    s_axi_rvalid <= 1;
                    case (s_axi_araddr)
                        14'h00: s_axi_rdata <= 32'h53323030;
                        14'h04: s_axi_rdata <= {26'b0, idle, hold, delay_sync[1], result_valid, run, ready};
                        14'h08: s_axi_rdata <= {31'b0, hold};
                        14'h0c: s_axi_rdata <= {14'b0, timing};
                        14'h10: s_axi_rdata <= {22'b0, count};
                        14'h14: s_axi_rdata <= summary;
                        14'h18: s_axi_rdata <= {27'b0, delay_value};
                        14'h1c: s_axi_rdata <= {25'b0, mode};
                        14'h20: s_axi_rdata <= 32'h424e4b31;
                        default: begin
                            s_axi_rdata <= 0;
                            s_axi_rresp <= 2'b10;
                        end
                    endcase
                end
            end
            if (reading_results) begin
                reading_results <= 0;
                s_axi_rdata <= result_q;
                s_axi_rvalid <= 1;
            end
        end
    end
endmodule
