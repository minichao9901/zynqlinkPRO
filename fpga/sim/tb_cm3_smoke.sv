`timescale 1ns/1ps
// Smoke test: drive the Cortex-M3 TAP directly and read IDCODE.
// Proves the encrypted DesignStart model elaborates and runs under XSim before
// any of our RTL is attached.
module tb_cm3_smoke;
    reg clk = 0;   always #5 clk = ~clk;
    reg rst_n = 0;
    reg trst_n = 0;
    reg tck = 0, tms = 1, tdi = 0;
    wire tdo, ntdoen, swdo, swdoen;
    wire [31:0] sys_dout;
    wire [15:0] sys_writes;

    cm3_target dut (
        .clk(clk), .rst_n(rst_n), .dbg_rst_n(rst_n), .trst_n(trst_n),
        .swclktck(tck), .swditms(tms), .tdi(tdi),
        .tdo(tdo), .ntdoen(ntdoen), .swdo(swdo), .swdoen(swdoen),
        .sys_dout(sys_dout), .sys_writes(sys_writes)
    );

    task tick(input t, input d, output r);
        begin
            #5 tms = t; tdi = d;
            #5 tck = 1;
            #5 tck = 0;
            #5 r = tdo;          // sample after the edge that shifted the bit out
        end
    endtask

    reg dummy;
    task idle_tck(input integer n);
        integer i;
        begin
            for (i = 0; i < n; i = i + 1) tick(1'b0, 1'b0, dummy);
        end
    endtask

    reg r;
    reg [31:0] idcode;
    integer i;

    initial begin
        #100 rst_n = 1;
        #100 trst_n = 1;
        // Test-Logic-Reset
        for (i = 0; i < 6; i = i + 1) tick(1'b1, 1'b0, r);
        // Run-Test/Idle
        tick(1'b0, 1'b0, r);

        // IR <- IDCODE (0xE), LSB first
        tick(1'b1, 1'b0, r);          // Select-DR
        tick(1'b1, 1'b0, r);          // Select-IR
        tick(1'b0, 1'b0, r);          // Capture-IR
        tick(1'b0, 1'b0, r);          // Shift-IR, bit0 = 0
        tick(1'b0, 1'b1, r);          // bit1 = 1
        tick(1'b0, 1'b1, r);          // bit2 = 1
        tick(1'b1, 1'b1, r);          // bit3 = 1, Exit1-IR
        tick(1'b1, 1'b0, r);          // Update-IR
        tick(1'b0, 1'b0, r);          // Run-Test/Idle

        // DR <- IDCODE, 32 bits
        tick(1'b1, 1'b0, r);          // Select-DR
        tick(1'b0, 1'b0, r);          // Capture-DR
        idcode = 32'd0;
        for (i = 0; i < 32; i = i + 1) begin
            tick(1'b0, 1'b0, r);      // Shift-DR
            idcode[i] = r;
        end
        tick(1'b1, 1'b0, r);          // Exit1-DR
        tick(1'b1, 1'b0, r);          // Update-DR
        tick(1'b0, 1'b0, r);          // Run-Test/Idle

        $display("JTAG IDCODE = %08h", idcode);
        if (idcode == 32'h4BA00477) begin
            $display("PASS CM3 JTAG IDCODE 4BA00477");
        end else begin
            $display("FAIL CM3 JTAG IDCODE got %08h", idcode);
            $fatal(1, "unexpected IDCODE");
        end
        $finish;
    end

    initial begin
        #2000000;
        $display("FAIL timeout");
        $fatal(1, "timeout");
    end
endmodule
