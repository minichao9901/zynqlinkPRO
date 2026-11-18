`timescale 1ns/1ps
module tb_jtag200;
    reg axi_clk = 0, axi_resetn = 0, fclk1 = 0, delay_ref = 0;
    realtime ref_half = 10.0;
    always #3.750 axi_clk = !axi_clk;
    always begin
        #(ref_half) fclk1 = !fclk1;
    end
    always #2.500 delay_ref = !delay_ref;

    wire phy_hold, ready, word_clk, word_reset, delay_load, delay_ready;
    wire [4:0] delay_value;
    wire [23:0] lane_word;
    wire [7:0] rx_word;
    wire tck, tms, tdi, tdo;

    reg [13:0] awaddr = 0, araddr = 0;
    reg [31:0] wdata = 0;
    wire [31:0] rdata;
    reg awvalid = 0, wvalid = 0, arvalid = 0;
    wire awready, wready, arready, bvalid, rvalid;
    wire [1:0] bresp, rresp;
    jtag200_regs regs (
        .axi_aclk(axi_clk), .axi_aresetn(axi_resetn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hf), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(1'b1),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(1'b1),
        .phy_hold(phy_hold), .ready(ready), .delay_ready(delay_ready),
        .delay_load(delay_load), .delay_value(delay_value), .word_clk(word_clk), .word_reset(word_reset),
        .lane_word(lane_word), .rx_word(rx_word)
    );
    jtag200_io io (
        .fclk1(fclk1), .delay_ref(delay_ref), .axi_clk(axi_clk), .axi_resetn(axi_resetn),
        .phy_hold(phy_hold), .word_clk(word_clk), .word_reset(word_reset), .ready(ready),
        .delay_load(delay_load), .delay_value(delay_value), .delay_ready(delay_ready),
        .lane_word(lane_word), .rx_word(rx_word), .tck(tck), .tms(tms), .tdi(tdi), .tdo(tdo)
    );
    jtag_dtm_model #(.RETURN_NS(0.80)) tap (
        .rst_n(axi_resetn), .tck(tck), .tms(tms), .tdi(tdi), .tdo(tdo)
    );

    task automatic write_reg(input [13:0] addr, input [31:0] data, input [1:0] response);
        fork
            begin
                repeat (addr[2] ? 2 : 1) @(negedge axi_clk);
                awaddr = addr;
                awvalid = 1;
                do @(posedge axi_clk); while (!awready);
                @(negedge axi_clk);
                awvalid = 0;
            end
            begin
                repeat (addr[2] ? 1 : 2) @(negedge axi_clk);
                wdata = data;
                wvalid = 1;
                do @(posedge axi_clk); while (!wready);
                @(negedge axi_clk);
                wvalid = 0;
            end
        join
        do @(posedge axi_clk); while (!bvalid);
        if (bresp !== response) $fatal(1, "AXI write response addr=%h got=%b expected=%b", addr, bresp, response);
    endtask

    task automatic read_reg(input [13:0] addr, output [31:0] data);
        @(negedge axi_clk);
        araddr = addr;
        arvalid = 1;
        do @(posedge axi_clk); while (!arready);
        @(negedge axi_clk);
        arvalid = 0;
        do @(posedge axi_clk); while (!rvalid);
        if (rresp !== 0) $fatal(1, "AXI read response addr=%h got=%b", addr, rresp);
        data = rdata;
    endtask

    task automatic wait_status(input [4:0] expected);
        reg [31:0] status;
        read_reg(4, status);
        for (int attempts = 0; status !== expected && attempts < 15000; attempts++)
            read_reg(4, status);
        if (status !== expected) $fatal(1, "Status %h expected %h", status, expected);
    endtask

    localparam PULSES = 312;
    reg [1:0] expected_pins [0:PULSES-1];
    reg watching = 0;
    integer rises = 0, falls = 0;
    realtime last_rise = 0, last_fall = 0, expected_period = 0;
    function automatic bit close(input realtime a, b);
        return a >= b - 0.020 && a <= b + 0.020;
    endfunction

    always @(posedge tck) begin
        if ($realtime > 150 && !watching)
            $fatal(1, "TCK edge outside scan at %t", $realtime);
        if (watching) begin
            if (rises >= PULSES) $fatal(1, "Extra TCK edge");
            if (rises && !close($realtime - last_rise, expected_period))
                $fatal(1, "TCK period %f ns expected %f ns", $realtime - last_rise, expected_period);
            if (rises && !close($realtime - last_fall, expected_period / 2))
                $fatal(1, "Incorrect low pulse width");
            if ({tms, tdi} !== expected_pins[rises])
                $fatal(1, "TMS/TDI bit %0d got %b expected %b", rises, {tms, tdi}, expected_pins[rises]);
            rises++;
            last_rise = $realtime;
        end
    end
    always @(negedge tck) if (watching) begin
        if (!close($realtime - last_rise, expected_period / 2))
            $fatal(1, "Incorrect high pulse width");
        falls++;
        last_fall = $realtime;
    end

    task automatic profile(input int n, input realtime half_ref, period);
        int fp, fp_rx, len;
        reg [31:0] word, status;
        fp = $fopen($sformatf("tx%0d.mem", n), "r");
        fp_rx = $fopen($sformatf("rx%0d.hex", n), "w");
        if (!$fscanf(fp, "%h", len)) $fatal(1, "Missing TX vector");
        write_reg(8, 2, 0);
        #100;
        ref_half = half_ref;
        #200;
        write_reg(8, 0, 0);
        wait_status(5);
        write_reg(12, 0, 0);
        for (int i = 0; i < len; i++) begin
            if (!$fscanf(fp, "%h", word)) $fatal(1, "Short TX vector");
            write_reg(14'h1000 + 4*i, word, 0);
        end
        $fclose(fp);

        expected_period = period;
        rises = 0;
        falls = 0;
        watching = 1;
        write_reg(8, 1, 0);
        write_reg(8, 2, 2);
        wait_status(15);
        if (rises != PULSES || falls != PULSES || tck !== 0)
            $fatal(1, "TCK counts %d/%d expected %d/%d", rises, falls, PULSES, PULSES);
        watching = 0;
        for (int i = 0; i < len; i++) begin
            read_reg(14'h2000 + 4*i, word);
            $fwrite(fp_rx, "%02x ", word[7:0]);
        end
        $fclose(fp_rx);
        write_reg(8, 0, 0);
        wait_status(5);
        #200;
        $display("J200_PROFILE %0d period=%0.3f ns pulses=%0d", n, period, rises);
    endtask

    initial begin
        $readmemh("pins.mem", expected_pins);
        #300;
        @(negedge axi_clk);
        axi_resetn = 1;
        profile(0, 10.0, 20.0);
        profile(1, 10.0, 15.0);
        profile(2, 12.5, 12.5);
        profile(3, 10.0, 10.0);
        profile(4, 12.5, 6.250);
        profile(5, 10.0, 5.0);
        $display("JTAG200_SIM_PASS");
        $finish;
    end

    initial begin
        #20000000;
        $fatal(1, "JTAG200 simulation timeout");
    end
endmodule
