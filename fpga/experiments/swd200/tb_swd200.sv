`timescale 1ns/1ps
module tb_swd200;
    bit axi_clk = 0, ref_clk = 0, delay_ref = 0, target_clk = 0;
    bit axi_resetn = 0, target_resetn = 0;
    reg [1:0] rate;
    wire word_clk, word_reset, delay_ready;
    wire [3:0] clk_slots, data_slots, release_slots, rx_slots;
    wire hold, delay_load;
    wire [4:0] taps;
    reg [13:0] awaddr = 0, araddr = 0;
    reg [31:0] wdata = 0;
    bit awvalid = 0, wvalid = 0, arvalid = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    wire swclk;
    tri1 swdio;
    wire target_data, target_drive;
    reg returned_data = 1, returned_drive = 0;
    realtime target_period = 10.0, ref_period;
    realtime return_ns = 0.8, clock_period;
    integer mhz = 200, words = 128, rounds = 3, tck_count = 0, waits = 0, ignored;
    integer trace = 0, tap_arg = 0, idle_arg = 2, ack_arg = 12, data_arg = 12;
    integer parity_edge = -1;
    wire flip_parity = tck_count == parity_edge;
    bit configured = 0;

    always #3.75 axi_clk = ~axi_clk;
    always #2.5 delay_ref = ~delay_ref;
    initial begin
        wait(configured);
        forever #(ref_period / 2.0) ref_clk = ~ref_clk;
    end
    initial begin
        wait(configured);
        forever #(target_period / 2.0) target_clk = ~target_clk;
    end
    always @(target_drive or target_data) begin
        returned_drive <= #(return_ns) (target_drive === 1'b1);
        returned_data <= #(return_ns) target_data;
    end
    assign swdio = returned_drive ? returned_data ^ flip_parity : 1'bz;

    swd200_phy phy (
        .fclk_ref(ref_clk), .axi_aclk(axi_clk), .axi_aresetn(axi_resetn), .hold(hold),
        .delay_ref(delay_ref), .delay_load(delay_load), .delay_value(taps), .delay_ready(delay_ready),
        .word_clk(word_clk), .word_reset(word_reset),
        .clk_slots(clk_slots), .data_slots(data_slots), .release_slots(release_slots), .rx_slots(rx_slots),
        .swclk(swclk), .swdio(swdio), .nsrst()
    );
    swd200_regs regs (
        .axi_aclk(axi_clk), .axi_aresetn(axi_resetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hf), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(1'b1),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(1'b1),
        .hold(hold), .delay_ready(delay_ready), .delay_load(delay_load), .delay_value(taps),
        .word_clk(word_clk), .word_reset(word_reset), .rx_slots(rx_slots),
        .clk_slots(clk_slots), .data_slots(data_slots), .release_slots(release_slots)
    );
    cm3_target #(.TRACE_LEVEL(0)) target (
        .clk(target_clk), .rst_n(target_resetn), .dbg_rst_n(target_resetn), .trst_n(1'b1),
        .swclktck(swclk), .swditms(swdio), .tdi(1'b0),
        .swdo(target_data), .swdoen(target_drive)
    );

    realtime last_rise = 0, last_fall = 0;
    integer adjacent = 0;
    bit timing_batch = 0;
    integer timed_edges, ack_gaps, request_gaps, wait_start;
    realtime batch_start, prev_timed_edge, ack_gap_ns, request_gap_ns;
    integer total_edges [0:1], total_ack_gaps [0:1], total_request_gaps [0:1], total_waits [0:1];
    realtime total_ack_ns [0:1], total_request_ns [0:1], total_control_ns [0:1];
    always @(posedge swclk) if (!word_reset) begin
        realtime extra_ns;
        if (last_fall != 0 && $realtime - last_fall < clock_period / 2.0 - 0.004)
            $fatal(1, "short SWCLK low %.3f ps", 1000.0 * ($realtime - last_fall));
        if (last_rise != 0 && $realtime - last_rise < clock_period - 0.004)
            $fatal(1, "short SWCLK period %.3f ns", $realtime - last_rise);
        if (last_rise != 0 && $realtime - last_rise < clock_period + 0.004) adjacent++;
        last_rise = $realtime;
        tck_count++;
        if (timing_batch) begin
            extra_ns = $realtime - prev_timed_edge - clock_period;
            if (timed_edges && extra_ns > 0.004) begin
                if (regs.batch.link.state == regs.batch.link.HEADER) begin
                    request_gaps++;
                    request_gap_ns += extra_ns;
                end else begin
                    ack_gaps++;
                    ack_gap_ns += extra_ns;
                end
            end
            timed_edges++;
            prev_timed_edge = $realtime;
        end
        if (trace && tck_count > 148 && tck_count < 212)
            $display("PIN bit=%0d t=%0.3f T=%b bus=%b targ=%b/%b", tck_count,
                     $realtime, phy.serial_release, swdio, returned_drive, returned_data);
    end
    always @(negedge swclk) if (!word_reset && last_rise != 0) begin
        if ($realtime - last_rise < clock_period / 2.0 - 0.004 ||
            $realtime - last_rise > clock_period / 2.0 + 0.004)
            $fatal(1, "SWCLK high width %.3f ns", $realtime - last_rise);
        last_fall = $realtime;
    end
    // Either side driving at once violates turnaround, even if values agree.
    always @(phy.serial_release or target_drive or returned_drive)
        if (!word_reset && (target_drive || returned_drive) && !phy.serial_release)
            $fatal(1, "SWDIO contention at %.3f ns, edge %0d", $realtime, tck_count);
    always @(posedge word_clk)
        if (trace && tck_count > 148 && tck_count < 212)
            $display("WORD t=%0.3f TX clk=%b dat=%b T=%b RX=%b state=%d captured=%h",
                     $realtime, clk_slots, data_slots, release_slots, rx_slots,
                     regs.batch.link.state, regs.batch.link.captured);

    task wr(input [13:0] address, input [31:0] data);
        @(negedge axi_clk);
        awaddr = address; wdata = data; awvalid = 1; wvalid = 1;
        @(posedge axi_clk);
        if (!awready || !wready) $fatal(1, "AXI write stalled addr=%h", address);
        @(negedge axi_clk);
        awvalid = 0; wvalid = 0;
        while (!bvalid) @(negedge axi_clk);
        if (bresp != 0) $fatal(1, "AXI write rejected addr=%h", address);
    endtask

    task rd(input [13:0] address, output [31:0] data, input [1:0] expected_response = 0);
        @(negedge axi_clk);
        araddr = address; arvalid = 1;
        @(posedge axi_clk);
        if (!arready) $fatal(1, "AXI read stalled addr=%h", address);
        @(negedge axi_clk);
        arvalid = 0;
        while (!rvalid) @(negedge axi_clk);
        if (rresp != expected_response) $fatal(1, "AXI read addr=%h resp=%h", address, rresp);
        data = rdata;
    endtask

    task put(input integer index, input [4:0] req, input [31:0] data);
        wr(14'h1000 + index * 8, {27'b0, req});
        wr(14'h1004 + index * 8, data);
    endtask

    task run_batch(input integer count, output [31:0] summary);
        reg [31:0] status;
        begin
            wr(14'h10, count);
            status = 0;
            while (!(status[2] && status[5])) begin
                rd(14'h04, status);
                if (status[4] || !status[0]) $fatal(1, "PHY reset during batch %h", status);
            end
            rd(14'h14, summary);
            waits += summary[31:16];
        end
    endtask

    task good_batch(input integer count);
        reg [31:0] summary;
        begin
            run_batch(count, summary);
            if (summary[15:0] !== count[15:0])
                $fatal(1, "batch expected=%0d completed=%0d ACK=%b parity_error=%b summary=%h edges=%0d",
                       count, summary[9:0], summary[12:10], summary[13], summary, tck_count);
        end
    endtask

    task timed_batch(input integer count, input integer direction, output realtime elapsed);
        timed_edges = 0;
        ack_gaps = 0;
        request_gaps = 0;
        wait_start = waits;
        ack_gap_ns = 0;
        request_gap_ns = 0;
        batch_start = $realtime;
        timing_batch = 1;
        good_batch(count);
        timing_batch = 0;
        elapsed = $realtime - batch_start;
        total_edges[direction] += timed_edges;
        total_ack_gaps[direction] += ack_gaps;
        total_request_gaps[direction] += request_gaps;
        total_waits[direction] += waits - wait_start;
        total_ack_ns[direction] += ack_gap_ns;
        total_request_ns[direction] += request_gap_ns;
        total_control_ns[direction] += elapsed - timed_edges * clock_period - ack_gap_ns - request_gap_ns;
    endtask

    task xfer(input [3:0] req, input [31:0] data, output [31:0] value);
        put(0, {1'b0, req}, data);
        good_batch(1);
        rd(14'h2000, value);
    endtask

    function [31:0] pattern(input integer index, input integer round_no);
        pattern = (32'h5a89cdef ^ (32'h9e3779b9 * index)) ^ (round_no * 32'h1327baad);
    endfunction

    reg [31:0] value, status;
    integer index, round_no, p;
    realtime batch_ns, write_ns, read_ns;
    integer guard_arg = 0;
    initial begin
        ignored = $value$plusargs("mhz=%d", mhz);
        ignored = $value$plusargs("return_ns=%f", return_ns);
        ignored = $value$plusargs("target_ns=%f", target_period);
        ignored = $value$plusargs("ack=%d", ack_arg);
        ignored = $value$plusargs("data=%d", data_arg);
        ignored = $value$plusargs("tap=%d", tap_arg);
        ignored = $value$plusargs("idle=%d", idle_arg);
        ignored = $value$plusargs("words=%d", words);
        ignored = $value$plusargs("rounds=%d", rounds);
        ignored = $value$plusargs("guard=%d", guard_arg);
        trace = $test$plusargs("trace");
        ref_period = mhz == 160 ? 25.0 : 20.0;
        clock_period = 1000.0 / mhz;
        rate = mhz == 50 ? 0 : mhz == 100 ? 1 : 2;
        $display("PROFILE SWCLK=%0d HCLK_period=%.3f return=%.3f ack=%0d data=%0d tap=%0d idle=%0d",
                 mhz, target_period, return_ns, ack_arg, data_arg, tap_arg, idle_arg);
        configured = 1;
        #200;
        axi_resetn = 1;
        target_resetn = 1;
        wr(14'h08, 0);
        status = 0;
        while (!status[0]) rd(14'h04, status);
        rd(14'h00, value);
        if (value != 32'h53323030) $fatal(1, "wrong PHY ID %h", value);
        wr(14'h18, tap_arg);
        wr(14'h1c, guard_arg << 4);
        wr(14'h0c, {14'b0, idle_arg[3:0], data_arg[5:0], ack_arg[5:0], rate});
        put(0, 5'h10, 0);
        good_batch(1);
        if (tck_count != 152) $fatal(1, "SWD entry length %0d", tck_count);
        xfer(4'h2, 0, value);
        if (value !== 32'h2ba01477) $fatal(1, "DPIDR mismatch: %h", value);
        xfer(4'h0, 32'h1e, value);
        xfer(4'h4, 32'h50000000, value);
        value = 0;
        for (p = 0; p < 32 && (value & 32'ha0000000) != 32'ha0000000; p++)
            xfer(4'h6, 0, value);
        if ((value & 32'ha0000000) !== 32'ha0000000) $fatal(1, "bad power handshake %h", value);
        xfer(4'h8, 0, value);
        xfer(4'h1, 32'h23000052, value);

        write_ns = 0;
        read_ns = 0;
        for (p = 0; p < 2; p++) begin
            total_edges[p] = 0;
            total_ack_gaps[p] = 0;
            total_request_gaps[p] = 0;
            total_waits[p] = 0;
            total_ack_ns[p] = 0;
            total_request_ns[p] = 0;
            total_control_ns[p] = 0;
        end
        for (round_no = 0; round_no < rounds; round_no++) begin
            put(0, 5'h5, 32'h60000000);
            for (index = 0; index < words; index++)
                put(index+1, 5'hd, pattern(index, round_no));
            put(words+1, 5'he, 0);
            timed_batch(words+2, 0, batch_ns);
            write_ns += batch_ns;
            for (index = 0; index < words; index++)
                if (target.u_sys.mem[index] !== pattern(index, round_no))
                    $fatal(1, "target SRAM write index=%0d stored=%h", index, target.u_sys.mem[index]);

            put(0, 5'h5, 32'h60000000);
            // The response to the first posted AP read is stale.
            for (index = 0; index < words; index++) put(index+1, 5'hf, 0);
            put(words+1, 5'he, 0);
            timed_batch(words+2, 1, batch_ns);
            read_ns += batch_ns;
            for (index = 0; index < words; index++) begin
                rd(14'h2000 + (index+2)*4, value);
                if (value !== pattern(index, round_no))
                    $fatal(1, "read round=%0d index=%0d got=%h expected=%h",
                           round_no, index, value, pattern(index, round_no));
            end
        end

        if ($test$plusargs("banks")) begin
            wr(14'h1c, (guard_arg<<4)|2);
            put(0,5'h5,32'h60000000);
            for (index=0;index<256;index++) begin
                wr(14'h3000+index*4,pattern(index,0));
                put(index+1,5'hd,pattern(index,0));
            end
            put(257,5'he,0);put(258,5'h6,0);
            wr(14'h1c,(guard_arg<<4)|9);
            put(0,5'h5,32'h60000000);
            for (index=0;index<256;index++) put(index+1,5'hf,0);
            put(257,5'he,0);put(258,5'h6,0);
            for (p=0;p<2;p++) begin
                wr(14'h1c,(guard_arg<<4)|2|(p<<2));good_batch(259);
                wr(14'h1c,(guard_arg<<4)|9|(p<<2));good_batch(259);
                for (index=0;index<256;index++) begin
                    rd(14'h2000+(index+2)*4,value);
                    if(value !== (pattern(index,0)^{32{p[0]}})) $fatal(1,"bank payload");
                end
            end
            wr(14'h33fc,~pattern(255,0));run_batch(259,status);
            if(status[15:0]!==16'h4103) $fatal(1,"last-word mismatch %h",status);
            wr(14'h33fc,pattern(255,0));good_batch(259);
            wr(14'h1c,guard_arg<<4);
            $display("RESIDENT_BANKS_PASS");
        end
        // Corrupt the target parity bit on the return wire. The second
        // command would emit 152 clocks and must be fenced by the error.
        put(0, 5'h2, 0);
        put(1, 5'h10, 0);
        p = tck_count;
        parity_edge = p + 44;
        run_batch(2, status);
        parity_edge = -1;
        if (status[15:0] !== 16'h6400 || tck_count - p != 46 + idle_arg)
            $fatal(1, "parity fence summary=%h edges=%0d", status, tck_count - p);
        rd(14'h2000, value, 2'b10); // A rejected command has no readable result.
        xfer(4'h2, 0, value);
        if (value !== 32'h2ba01477) $fatal(1, "DPIDR after parity fault %h", value);
        if (adjacent < 128) $fatal(1, "missing continuous SWCLK pulses");
        for (p = 0; p < 2; p++)
            $display("SWD200_COST dir=%0s batch_ns=%.3f edges=%0d wire_ns=%.3f ack_gaps=%0d ack_gap_ns=%.3f request_gaps=%0d request_gap_ns=%.3f control_ns=%.3f waits=%0d",
                     p ? "read" : "write", p ? read_ns : write_ns, total_edges[p],
                     total_edges[p] * clock_period, total_ack_gaps[p], total_ack_ns[p],
                     total_request_gaps[p], total_request_ns[p], total_control_ns[p], total_waits[p]);
        $display("SWD200_PASS mhz=%0d words=%0d rounds=%0d reads_MBps=%.4f writes_MBps=%.4f waits=%0d edges=%0d",
                 mhz, words, rounds, 4000.0*words*rounds/read_ns, 4000.0*words*rounds/write_ns, waits, tck_count);
        $finish;
    end
    initial begin
        #10_000_000;
        $fatal(1, "testbench deadline");
    end
endmodule
