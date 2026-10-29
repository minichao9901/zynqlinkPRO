`timescale 1ns/1ps
// Cycle budget of one chained AP read through jtag_core.
// Drives the same next_valid/next_ready chain the block engine uses, then
// reports FCLK cycles and TCK cycles per word plus a per-state histogram.
module tb_jtag_word_cost;
    real clkns = 8.333333;
    integer late = 0;
    integer idle = 0;
    reg clk = 0;
    initial begin
        $value$plusargs("clkns=%f", clkns);
        $value$plusargs("late=%d", late);
        $value$plusargs("idle=%d", idle);
        forever #(clkns/2.0) clk = ~clk;
    end

    reg rst_n=0,start=0,invalidate=0;
    reg [2:0] op=0;
    reg [7:0] req=0;
    reg [31:0] wd=0;
    wire busy,valid,tck,tms,tdi;
    wire [2:0] ack;
    wire [31:0] data;

    wire chain=1'b1,dummy_first=1'b0;
    wire tdummy,tdap;
    wire dap_in = chain && !dummy_first ? tdummy : tdi;
    wire dummy_in = dummy_first ? tdap : tdi;
    wire tap_output = chain && dummy_first ? tdummy : tdap;

    jtag_dp_model #(.RETURN_NS(0)) ap(
        .rst_n(rst_n),.tck(tck),.tms(tms),.tdi(dap_in),.tdo(tdap));
    jtag_dp_model #(.IRLEN(5),.DUMMY(1),.RETURN_NS(0)) dummy(
        .rst_n(rst_n),.tck(tck),.tms(tms),.tdi(dummy_in),.tdo(tdummy));

    reg tdo_q = 1;
    always @(tap_output) tdo_q <= #(12.0) tap_output;
    wire tdo = tdo_q;

    reg next_valid = 0;
    reg [7:0] next_request = 8'h0f;
    reg [31:0] next_wdata = 0;

    jtag_core dut(.idcode_ir(8'h0e),.riscv_mode(1'b0),.clk(clk),.rst_n(rst_n),.start(start),.invalidate(invalidate),
        .operation(op),.request(req),.wdata(wd),.seq_count(9'd0),.seq_data(256'd0),
        .seq_tms(1'b0),.ir_length(8'd4),.ir_before(11'd0),.ir_after(11'd5),
        .dr_before(8'd0),.dr_after(8'd1),.half_delay(4'd0),.idle_cycles(idle[3:0]),
        .late_return(late[0]),.tdo(tdo),.next_valid(next_valid),
        .next_request(next_request),.next_wdata(next_wdata),
        .next_ready(next_ready),.result_valid(valid),.busy(busy),
        .ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),
        .cached_instruction(),.cache_valid(),.sequence_result(),
        .fence_req(1'b0),.fence_done(),.fence_error());

    integer fclk_cycles = 0, tck_cycles = 0, words = 0, budget = 0;
    integer last_fclk = 0, last_tck = 0;
    integer state_cycles [0:15];
    integer word_fclk [0:31];
    integer word_tck [0:31];
    integer i;
    always @(posedge clk) begin
        fclk_cycles = fclk_cycles + 1;
        if (rst_n) state_cycles[dut.state] = state_cycles[dut.state] + 1;
    end
    always @(posedge tck) tck_cycles = tck_cycles + 1;

    always @(posedge clk) begin
        if (valid && rst_n) begin
            if (words < 32) begin
                word_fclk[words] = fclk_cycles - last_fclk;
                word_tck[words]  = tck_cycles - last_tck;
            end
            last_fclk = fclk_cycles;
            last_tck  = tck_cycles;
            words = words + 1;
        end
    end

    initial begin
        for (i=0;i<16;i=i+1) state_cycles[i]=0;
        repeat(5) @(negedge clk);
        rst_n = 1;
        repeat(2) @(negedge clk);
        // Prime one AP read, then hold the chain high exactly like the engine.
        @(negedge clk); op=3'd0; req=8'h0f; wd=32'd0; start=1;
        @(negedge clk); start=0; next_valid=1;
        while (words < 20 && budget < 200000) begin
            @(negedge clk); budget = budget + 1;
        end
        $display("words=%0d ack_last=%0d data=%08x", words, ack, data);
        $display("steady per-word FCLK cycles:");
        for (i=2;i<8;i=i+1) $display("  word%0d fclk=%0d tck=%0d", i, word_fclk[i], word_tck[i]);
        $display("state histogram (cycles): IDLE=%0d ROUTE=%0d RESET=%0d IR_NAV=%0d IR_PRE=%0d IR_VALUE=%0d IR_POST=%0d IR_EXIT=%0d DR_NAV=%0d DR_PRE=%0d DR_VALUE=%0d DR_POST=%0d DR_EXIT=%0d EVAL=%0d DONE=%0d PHYWAIT=%0d",
            state_cycles[0],state_cycles[1],state_cycles[2],state_cycles[3],
            state_cycles[4],state_cycles[5],state_cycles[6],state_cycles[7],
            state_cycles[8],state_cycles[9],state_cycles[10],state_cycles[11],
            state_cycles[12],state_cycles[13],state_cycles[14],state_cycles[15]);
        $display("stats: cycles=%0d bits=%0d transfers=%0d ratio=%0.3f",
            dut.stat_cycles, dut.stat_bits, dut.stat_transfers,
            dut.stat_cycles / (2.0 * dut.stat_bits));
        $finish;
    end
endmodule
