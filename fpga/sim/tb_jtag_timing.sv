`timescale 1ns/1ps
// Reproduce the board's TDO-return timing across FCLK periods.
// The physical round trip is one absolute delay after the DAP model drives TDO,
// so shrinking the FCLK period eats the capture margin exactly as on hardware.
// Timing comes from sim_cfg.txt: "<FCLK ps> <TDO round trip ps> <late 0|1>".
module tb_jtag_timing;
    real clkns = 8.333333;
    real tdons = 12.0;
    integer mode = 0;
    reg cfg_ready = 0;

    reg clk = 0;
    initial begin
        integer fd, clk_ps, tdo_ps, late_v;
        fd = $fopen("sim_cfg.txt", "r");
        if (fd != 0) begin
            if ($fscanf(fd, "%d %d %d", clk_ps, tdo_ps, late_v) == 3) begin
                clkns = clk_ps / 1000.0;
                tdons = tdo_ps / 1000.0;
                mode  = late_v;
            end
            $fclose(fd);
        end
        cfg_ready = 1;
        forever #(clkns/2.0) clk = ~clk;
    end

    reg rst_n=0,start=0,invalidate=0;
    reg [2:0] op=0;
    reg [7:0] req=0;
    reg [31:0] wd=0;
    wire busy,valid,tck,tms,tdi;
    wire [2:0] ack;
    wire [31:0] data;

    // Two-TAP chain: F103 boundary TAP before the ARM DAP, the arrangement the
    // board's DAP_JTAG_AutoConfigure reports (IR 4 then 5, one bypass DR bit).
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
    always @(tap_output) tdo_q <= #(tdons) tap_output;
    wire tdo = tdo_q;
    reg tdo_rise=1,tdo_fall=1;
    always @(posedge clk) tdo_rise<=tdo;
    always @(negedge clk) tdo_fall<=tdo;

    jtag_core dut(.idcode_ir(8'h0e),.riscv_mode(1'b0),.clk(clk),.rst_n(rst_n),.start(start),.invalidate(invalidate),
        .operation(op),.request(req),.wdata(wd),.seq_count(9'd0),.seq_data(256'd0),
        .seq_tms(1'b0),.ir_length(8'd4),.ir_before(11'd0),.ir_after(11'd5),
        .dr_before(8'd0),.dr_after(8'd1),.half_delay(4'd0),.idle_cycles(4'd1),
        .late_return(mode[4]),.tdo(mode[0] ? tdo_rise : tdo_fall),.next_valid(1'b0),.next_request(8'd0),
        .next_wdata(32'd0),.next_ready(),.result_valid(valid),.busy(busy),
        .ack(ack),.rdata(data),.tck(tck),.tms(tms),.tdi(tdi),
        .cached_instruction(),.cache_valid(),.sequence_result(),
        .fence_req(1'b0),.fence_done(),.fence_error());

    task fail(input [255:0] msg);
        begin
            $display("RESULT clkns=%0.3f tdons=%0.1f mode=%0d FAIL %0s",
                     clkns, tdons, mode, msg);
            $finish;
        end
    endtask

    task call(input [2:0] operation,input [7:0] request,input [31:0] value,
              input [2:0] expected_ack);
        integer budget;
        begin
            @(negedge clk); op=operation; req=request; wd=value; start=1;
            @(negedge clk); start=0; budget=0;
            while(!valid && budget<20000) begin @(negedge clk); budget=budget+1; end
            if(!valid) fail("timeout");
            if(ack!==expected_ack) fail("bad ack");
            @(negedge clk);
        end
    endtask

    task configure_mem;
        begin
            call(0,8'h08,32'h00000000,1);
            call(0,8'h01,32'h23000012,1);
            call(0,8'h05,32'h20000000,1);
        end
    endtask

    integer i;
    task read_pattern;
        begin
            configure_mem();
            call(0,8'h0f,0,1);                    // prime the posted pipeline
            for(i=0;i<16;i=i+1) begin
                call(0, i==15 ? 8'h0e : 8'h0f, 0, 1);
                if(data!==32'h12340000+i) fail("posted burst");
            end
        end
    endtask

    initial begin
        wait(cfg_ready);
        for(i=0;i<64;i=i+1) ap.mem[i]=32'h12340000+i;
        repeat(5) @(negedge clk);
        rst_n=1;
        repeat(3) @(negedge clk);
        // 1. IDCODE has no TDI payload, so a capture shift can still decode.
        call(3,0,0,1);
        if(data!==32'h4ba00477) fail("idcode");
        // 2. Posted AP reads and a completed AP write.
        read_pattern();
        configure_mem();
        call(0,8'h0d,32'habcdef01,1);
        call(0,8'h0e,0,1);
        if(ap.mem[0]!==32'habcdef01) fail("ap write");
        ap.mem[0]=32'h12340000;
        $display("RESULT clkns=%0.3f tdons=%0.1f mode=%0d PASS", clkns, tdons, mode);
        $finish;
    end

    initial begin #5000000; fail("watchdog"); end
endmodule
