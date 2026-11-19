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
    wire tck, tms, tdi, tdo, ntrst, nsrst;

    reg [13:0] awaddr = 0, araddr = 0;
    reg [31:0] wdata = 0;
    wire [31:0] rdata;
    reg awvalid = 0, wvalid = 0, arvalid = 0;
    wire awready, wready, arready, bvalid, rvalid;
    wire [1:0] bresp, rresp;
    jtag200_regs #(.ENABLE_BLOCK(1)) regs (
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
        .lane_word(lane_word), .rx_word(rx_word), .tck(tck), .tms(tms), .tdi(tdi), .tdo(tdo),
        .ntrst(ntrst), .nsrst(nsrst)
    );
    reg block_test = 0;
    wire raw_tdo, block_tdo;
    jtag_dtm_model #(.RETURN_NS(0.80)) tap (
        .rst_n(axi_resetn && ntrst && nsrst), .tck(tck && !block_test),
        .tms(tms), .tdi(tdi), .tdo(raw_tdo)
    );
`ifdef J200_TEST_HAZARD3
    reg hazard_resetn = 0;
    jtag200_hazard_target sba (
        .resetn(hazard_resetn), .tck(tck && block_test),
        .tms(tms), .tdi(tdi), .tdo(block_tdo)
    );
`else
    riscv_sba_model #(.RETURN_NS(0.80)) sba (
        .rst_n(axi_resetn && ntrst && nsrst), .tck(tck && block_test),
        .tms(tms), .tdi(tdi), .tdo(block_tdo)
    );
`endif
    reg arm_test = 0;
    wire boundary_tdo, arm_tdo;
`ifndef J200_TEST_HAZARD3
    // As on H743, the four-bit DAP is nearest TDO and the five-bit
    // boundary TAP is nearest TDI. The boundary TAP is in BYPASS.
    jtag_dp_model #(.IRLEN(5),.DUMMY(1),.RETURN_NS(0.2)) boundary (
        .rst_n(axi_resetn), .tck(tck && arm_test), .tms(tms), .tdi(tdi), .tdo(boundary_tdo));
    jtag_dp_model #(.RETURN_NS(0.8)) arm_dap (
        .rst_n(axi_resetn), .tck(tck && arm_test), .tms(tms), .tdi(boundary_tdo), .tdo(arm_tdo));
`endif
`ifdef J200_TEST_CM3
    reg hclk = 0;
    real hclk_mhz = 48;
    initial begin
        if ($value$plusargs("hclk=%f",hclk_mhz)) begin end
        forever #(500.0/hclk_mhz) hclk = !hclk;
    end
    wire cm3_tdo, cm3_ntdoen;
    cm3_target #(.WORDS(1024),.ADDR_BITS(10)) cm3 (
        .clk(hclk),.rst_n(axi_resetn),.dbg_rst_n(axi_resetn),.trst_n(axi_resetn),
        .swclktck(tck),.swditms(tms),.tdi(boundary_tdo),.tdo(cm3_tdo),.ntdoen(cm3_ntdoen));
    assign #0.80 tdo = cm3_ntdoen ? 1'b1 : cm3_tdo;
`else
    assign tdo = arm_test ? arm_tdo : block_test ? block_tdo : raw_tdo;
`endif

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
        for (int attempts = 0; status !== expected && attempts < 180000; attempts++)
            read_reg(4, status);
        if (status !== expected) $fatal(1, "Status %h expected %h", status, expected);
    endtask

    localparam PULSES = 312;
    reg [1:0] expected_pins [0:PULSES-1];
    reg watching = 0;
    integer rises = 0, falls = 0, measured_tck = 0;
    reg most_recent_tms = 1, most_recent_tdi = 1;
    // Validate the low-clock boundary on the actual serializer input.
    always @(posedge word_clk) begin
        if (word_reset || !regs.block_mode_sync[1]) begin
            most_recent_tms = 1;
            most_recent_tdi = 1;
        end else if (block_test) begin
            if (regs.pipeline.engine.active_half == 2) begin
                for (integer group=0; group<2; group=group+1) begin
                    if (lane_word[4*group+2]) begin
                        most_recent_tms = lane_word[10+4*group];
                        most_recent_tdi = lane_word[18+4*group];
                    end else if ({lane_word[8+4*group+:4],lane_word[16+4*group+:4]} !==
                                 {{4{most_recent_tms}},{4{most_recent_tdi}}})
                        $fatal(1,"TMS/TDI changed in a parked-clock 100 MHz slot");
                end
            end else begin
                for (integer pair=0; pair<4; pair=pair+1) begin
                    if (lane_word[2*pair+1]) begin
                        most_recent_tms = lane_word[8+2*pair+1];
                        most_recent_tdi = lane_word[16+2*pair+1];
                    end else if (lane_word[7:0] != 8'hf0 &&
                        ({lane_word[8+2*pair+:2],lane_word[16+2*pair+:2]} !==
                         {{2{most_recent_tms}},{2{most_recent_tdi}}}))
                        $fatal(1,"TMS/TDI changed in a parked-clock slot");
                end
            end
        end
    end

    realtime last_rise = 0, last_fall = 0, expected_period = 0;
    function automatic bit close(input realtime a, b);
        return a >= b - 0.020 && a <= b + 0.020;
    endfunction

    always @(posedge tck) begin
        if (block_test) measured_tck++;
        if ($realtime > 150 && !watching && !block_test)
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
        if ({ntrst, nsrst} !== 2'b11) $fatal(1, "Target reset held active");
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

`ifndef J200_TEST_HAZARD3
    task automatic pipeline(input int half, offset, idle, count, input bit fault);
        reg [31:0] info, word;
        integer before_scans, before_writes;
        write_reg(8, 2, 0);
        #200;
        write_reg(8, 0, 0);
        wait_status(5);
        read_reg(14'h010, info);
        if (info !== 32'h50495045) $fatal(1,"Missing pipeline capability");
        write_reg(14'h014, 32'h80020000, 0);
        write_reg(14'h018, count, 0);
        write_reg(14'h01c, (half == 2 ? 32'h00180000 : 0) |
                   (idle << 10) | (offset << 3) | half, 0);
        write_reg(8, 13, 2);
        write_reg(14'h014, 32'h0105f000, 0);
        for (int i=0; i<count; i++)
            write_reg(14'h1004+4*i, 32'h18adb000 ^ (i*32179), 0);
        before_scans=sba.dmi_scans;
        before_writes=sba.bus_writes;
        if (fault) sba.fault_next=1;
        write_reg(8, 13, 0);
        wait_status(15);
        read_reg(14'h020, info);
        if (info !== (fault ? 32'd4 : 32'd1))
            $fatal(1,"Block write completion %h fault=%d",info,fault);
        if (sba.bus_writes-before_writes != count) $fatal(1,"Write lost or replayed");
        if (sba.dmi_scans-before_scans > count+15) $fatal(1,"Write did not pipeline");
        for (int i=0; i<count; i++)
            if(sba.mem['h7000/4+i] !== (32'h18adb000 ^ (i*32179))) $fatal(1,"Target write mismatch %d",i);
        write_reg(8, 0, 0);
        wait_status(5);
        if (!fault) begin
            before_scans=sba.dmi_scans;
            write_reg(8, 5, 0);
            wait_status(15);
            read_reg(14'h020, info);
            if (info !== 1) $fatal(1,"Block read completion %h",info);
            read_reg(14'h2000, info);
            if (info !== (32'h00010000|count)) $fatal(1,"Block read header %h",info);
            read_reg(14'h27e0, info);
            if (info[2:0] !== 3'b011) $fatal(1,"Read diagnostics flags %h",info);
            read_reg(14'h27ec, info);
            if (info[1:0] !== 0 || info[31:2] !== 30'h18adb000)
                $fatal(1,"First SBA response diagnosis %h",info);
            for (int i=0; i<count; i++) begin
                read_reg(14'h2004+4*i, word);
                if(word !== (32'h18adb000 ^ (i*32179))) $fatal(1,"Host read mismatch %d %h",i,word);
            end
            if (sba.dmi_scans-before_scans > count+15) $fatal(1,"Read did not pipeline");
            write_reg(8, 0, 0);
            wait_status(5);
        end
        $display("J200_PIPELINE_PASS half=%0d idle=%0d words=%0d bus_fault=%0d",half,idle,count,fault);
    endtask

    bit profile_arm = 0;
    int arm_send_words, arm_return_words, arm_idle_words, arm_dr_setup_words;
    always @(posedge word_clk) if (profile_arm) begin
        if (regs.pipeline.engine.arm_stream.sending ||
            regs.pipeline.engine.phy.state == regs.pipeline.engine.phy.SEND)
            arm_send_words++;
        else if (regs.pipeline.engine.arm_stream.running ||
                 regs.pipeline.engine.phy.state == regs.pipeline.engine.phy.RETURN)
            arm_return_words++;
        else begin
            arm_idle_words++;
            if (regs.pipeline.engine.core.state == regs.pipeline.engine.core.DR_NAV ||
                regs.pipeline.engine.core.state == regs.pipeline.engine.core.DR_PRE)
                arm_dr_setup_words++;
        end
    end

    task automatic start_arm_profile;
        {arm_send_words, arm_return_words, arm_idle_words, arm_dr_setup_words} = 0;
        profile_arm = 1;
    endtask

    task automatic end_arm_profile(input string direction, input int idle, count,
                                   input int first_tck, input realtime ns);
        profile_arm = 0;
        $display("J200_ARM_BREAKDOWN direction=%s idle=%0d words=%0d wall_ns=%0.2f tck=%0d send_clkdiv=%0d return_clkdiv=%0d parked_clkdiv=%0d dr_prep_clkdiv=%0d",
                 direction,idle,count,ns,measured_tck-first_tck,arm_send_words,arm_return_words,
                 arm_idle_words,arm_dr_setup_words);
    endtask

    task automatic arm_pipeline(input int half, offset, idle, count, input bit stream);
        reg [31:0] word, invert;
        int first_tck;
        realtime started, write_ns, read_ns;
        write_reg(14'h018, count, 0);
        invert = stream ? 32'hffffffff : 0;
        write_reg(14'h01c, (stream ? 32'h00e00000 : 32'h00200000) |
                   (half == 2 ? 32'h00180000 : 0) |
                   (idle << 10) | (offset << 3) | half, 0);
        write_reg(14'h014, 32'h08000000, 0);
        write_reg(8, 13, 2);
        write_reg(14'h014, 32'h240503fc, 0);
        write_reg(8, 13, 2);
`ifdef J200_TEST_CM3
        write_reg(14'h014, 32'h200083fc, 0);
        write_reg(8, 13, 2);
        write_reg(14'h014, 32'h20008400, 0);
        write_reg(8, 13, 2);
        write_reg(14'h014, 32'h20008000, 0);
`else
        write_reg(14'h014, 32'h24050000, 0);
`endif
        for (int i=0; i<count; i++)
            write_reg(14'h1004+4*i, 32'h70420000 ^ (i*65537), 0);
        first_tck=measured_tck;
        start_arm_profile();
        started=$realtime;
        write_reg(8, stream ? 29 : 13, 0);
        wait_status(15);
        write_ns=$realtime-started;
        end_arm_profile("write",idle,count,first_tck,write_ns);
        read_reg(14'h020, word);
        if (word !== 1) $fatal(1,"ARM write completion %h",word);
        for (int i=0; i<count; i++) begin
`ifdef J200_TEST_CM3
            word = cm3.u_sys.mem[i];
`else
            word = arm_dap.mem[i];
`endif
            if (word !== (32'h70420000 ^ (i*65537) ^ invert))
                $fatal(1,"ARM write differs at word %d",i);
        end
        write_reg(8, 0, 0);
        wait_status(5);
        first_tck=measured_tck;
        start_arm_profile();
        started=$realtime;
        write_reg(8, stream ? 21 : 5, 0);
        wait_status(15);
        read_ns=$realtime-started;
        end_arm_profile("read",idle,count,first_tck,read_ns);
        read_reg(14'h020, word);
        if (word !== 1) $fatal(1,"ARM read completion %h",word);
        read_reg(14'h2000, word);
        if (word !== (32'h00010000|count)) $fatal(1,"ARM read header %h",word);
        for (int i=0; i<count; i++) begin
            read_reg(14'h2004+4*i, word);
            if (word !== (32'h70420000 ^ (i*65537) ^ invert)) $fatal(1,"ARM read differs at word %d",i);
        end
        write_reg(8, 0, 0);
        wait_status(5);
        $display("J200_ARM_PASS stream=%0d half=%0d idle=%0d words=%0d read_MBps=%0.3f write_MBps=%0.3f",
                 stream,half,idle,count,count*4000.0/read_ns,count*4000.0/write_ns);
    endtask

    task automatic check_arm_stream_errors;
        reg [31:0] word;
        int before_writes;
        write_reg(14'h1400, 0, 0);  // corrupt only the last expected word
        write_reg(8, 21, 0);
        wait_status(15);
        read_reg(14'h020, word);
        if (word !== 8) $fatal(1,"Final posted word mismatch escaped comparison: %h",word);
        write_reg(8, 0, 0);
        wait_status(5);
        before_writes=arm_dap.ap_writes;
        fork
            begin
                wait (regs.pipeline.engine.arm_stream.sending && regs.pipeline.engine.arm_stream.sent == 1);
                @(negedge tck);
                arm_dap.wait_scans=1;
            end
            write_reg(8, 13, 0);
        join
        wait_status(15);
        read_reg(14'h020, word);
        if (word !== 2 || arm_dap.ap_writes-before_writes != 3)
            $fatal(1,"WAIT replayed or issued another write: code %h, writes %0d",
                   word,arm_dap.ap_writes-before_writes);
        write_reg(8, 0, 0);
        wait_status(5);
        write_reg(14'h01c, 32'h00600000 | (3 << 10) | (29 << 3) | 2, 0);
        fork
            begin
                wait (regs.pipeline.engine.arm_stream.sending && regs.pipeline.engine.arm_stream.sent == 1);
                @(negedge tck);
                arm_dap.fault_next=1;
            end
            write_reg(8, 5, 0);
        join
        wait_status(15);
        read_reg(14'h020, word);
        if (word !== 4 || regs.pipeline.engine.arm_stream.status !== 0)
            $fatal(1,"The final CTRL/STAT fence missed a sticky AP fault: %h",word);
        write_reg(8, 0, 0);
        wait_status(5);
        $display("J200_ARM_STREAM_ERROR_PASS final_compare WAIT_no_replay sticky_fence");
    endtask

`else
    task automatic hazard_burst(input int half, offset, idle, count);
        reg [31:0] status, word, scans_wr, bits_wr, scans_total, bits_total, busy, invalid;
        integer cycles_before, write_tck, read_tck;
        realtime started, write_ns, read_ns;
        write_reg(8, 2, 0);
        hazard_resetn=0;
        #200;
        hazard_resetn=1;
        write_reg(8, 0, 0);
        wait_status(5);
        write_reg(14'h014, 32'h0105f000, 0);
        write_reg(14'h018, count, 0);
        write_reg(14'h01c, (half == 2 ? 32'h00180000 : 0) |
                   (idle << 10) | (offset << 3) | half, 0);
        for (int i=0; i<count; i++)
            write_reg(14'h1004+4*i, 32'h906da150 ^ (i*3697), 0);
        cycles_before = measured_tck;
        started=$realtime;
        write_reg(8, 13, 0);
        wait_status(15);
        write_ns=$realtime-started;
        write_tck=measured_tck-cycles_before;
        read_reg(14'h020,status);
        read_reg(14'h024,bits_wr);
        read_reg(14'h028,scans_wr);
        read_reg(14'h02c,busy);
        read_reg(14'h030,invalid);
        write_reg(8,0,0);
        wait_status(5);
        if (status!=1) begin
            $display("J200_HAZARD3_LIMIT phase=write half=%0d idle=%0d code=%h dmi_busy=%0d dmi_invalid=%0d tck=%0d scans=%0d",
                     half,idle,status,busy,invalid,write_tck,scans_wr);
        end else begin
            if (write_tck != bits_wr) $fatal(1,"Pipeline TX pulse counter differs: %d != %d",write_tck,bits_wr);
            for (int i=0; i<count; i++) begin
                if (sba.dut.u_memory.mem['h1f000/4+i] !== (32'h906da150 ^ (i*3697)))
                    $fatal(1,"Hazard3 SRAM write mismatch %d",i);
            end
            cycles_before=measured_tck;
            started=$realtime;
            write_reg(8, 5, 0);
            wait_status(15);
            read_ns=$realtime-started;
            read_tck=measured_tck-cycles_before;
            read_reg(14'h020,status);
            read_reg(14'h024,bits_total);
            read_reg(14'h028,scans_total);
            read_reg(14'h02c,busy);
            read_reg(14'h030,invalid);
            if (status!=1) begin
                $display("J200_HAZARD3_LIMIT phase=read half=%0d idle=%0d code=%h dmi_busy=%0d dmi_invalid=%0d tck=%0d",
                         half,idle,status,busy,invalid,read_tck);
            end else begin
                if (read_tck != bits_total-bits_wr) $fatal(1,"Pipeline RX pulse count differs");
                read_reg(14'h2000,word);
                if (word != (32'h00010000 | count)) $fatal(1,"Hazard3 pipeline header differs");
                for (int i=0; i<count; i++) begin
                    read_reg(14'h2004+4*i,word);
                    if (word !== (32'h906da150 ^ (i*3697))) $fatal(1,"Hazard3 SRAM read mismatch %d",i);
                end
                $display("J200_HAZARD3_PASS half=%0d idle=%0d words=%0d write_tck=%0d read_tck=%0d write_scans=%0d read_scans=%0d write_ns=%0.2f read_ns=%0.2f write_MBps=%0.3f read_MBps=%0.3f",
                         half,idle,count,write_tck,read_tck,scans_wr,scans_total-scans_wr,write_ns,read_ns,
                         count*4000.0/write_ns,count*4000.0/read_ns);
            end
            write_reg(8,0,0);
            wait_status(5);
        end
    endtask
`endif

    initial begin
        `ifndef J200_TEST_HAZARD3
`ifndef J200_TEST_CM3
        $readmemh("pins.mem", expected_pins);
`endif
`endif
        #300;
        @(negedge axi_clk);
        axi_resetn = 1;
`ifdef J200_TEST_HAZARD3
        block_test=1;
        if ($test$plusargs("hundred")) begin
            hazard_burst(2,29,192,128);
            hazard_burst(2,29,64,128);
            hazard_burst(2,29,32,128);
            hazard_burst(2,29,16,128);
            hazard_burst(2,29,12,128);
            hazard_burst(2,29,10,128);
            hazard_burst(2,29,8,128);
        end else if ($test$plusargs("fine")) begin
            hazard_burst(1,29,32,128);
            hazard_burst(1,29,28,128);
            hazard_burst(1,29,24,128);
            hazard_burst(1,29,20,128);
            hazard_burst(1,29,18,128);
            hazard_burst(1,29,16,128);
        end else begin
            hazard_burst(4,28,64,128);
            hazard_burst(4,28,16,128);
            hazard_burst(1,29,256,128);
            hazard_burst(1,29,128,128);
            hazard_burst(1,29,64,128);
            hazard_burst(1,29,32,128);
            hazard_burst(1,29,16,128);
            hazard_burst(1,29,8,128);
        end
`else
`ifdef J200_TEST_CM3
        begin
            integer half, sample_slot, idle, streaming;
            block_test=1;
            arm_test=1;
            if (!$value$plusargs("ref=%f",ref_half)) ref_half=10.0;
            if (!$value$plusargs("half=%d",half)) half=2;
            if (!$value$plusargs("sample=%d",sample_slot)) sample_slot=29;
            if (!$value$plusargs("idle=%d",idle)) idle=17;
            if (!$value$plusargs("stream=%d",streaming)) streaming=(half==2);
            write_reg(8,2,0);
            #500;
            write_reg(8,0,0);
            wait_status(5);
            arm_pipeline(half,sample_slot,idle,256,streaming);
            $display("J200_CM3_PASS HCLK_MHz=%0.3f ref_half_ns=%0.3f",hclk_mhz,ref_half);
        end
`else
        profile(0, 10.0, 20.0);
        profile(1, 10.0, 15.0);
        profile(2, 12.5, 12.5);
        profile(3, 10.0, 10.0);
        profile(4, 12.5, 6.250);
        profile(5, 10.0, 5.0);
        profile(6, 15.0, 15.0);
        // The firmware uses IO PLL 1.6 GHz and integer FCLK1 dividers.
        profile(7, 48/3.2, 48/6.4);
        profile(8, 43/3.2, 43/6.4);
        profile(9, 39/3.2, 39/6.4);
        profile(10, 38/3.2, 38/6.4);
        profile(11, 37/3.2, 37/6.4);
        profile(12, 36/3.2, 36/6.4);
        profile(13, 35/3.2, 35/6.4);
        profile(14, 34/3.2, 34/6.4);
        profile(15, 33/3.2, 33/6.4);
        write_reg(8, 2, 0);
        #200;
        ref_half = 10.0;
        block_test=1;
        pipeline(4,28,64,128,0);
        pipeline(2,29,64,128,0);
        pipeline(1,29,256,128,0);
        pipeline(1,29,256,32,1);
        arm_test=1;
        arm_pipeline(1,29,5,128,0);
        arm_pipeline(2,29,5,128,0);
        arm_pipeline(2,29,3,256,1);
        write_reg(8, 2, 0);
        #200;
        ref_half = 15.0;
        #300;
        write_reg(8, 0, 0);
        wait_status(5);
        arm_pipeline(2,29,3,256,0);
        arm_pipeline(2,29,1,256,1);
        arm_pipeline(2,29,3,256,1);
        arm_pipeline(2,30,5,256,1);
        check_arm_stream_errors();
`endif
`endif
        $display("JTAG200_SIM_PASS");
        $finish;
    end

    initial begin
        #20000000;
        $fatal(1, "JTAG200 simulation timeout");
    end
endmodule
