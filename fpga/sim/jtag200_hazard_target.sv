`timescale 1ns/1ps
// The real Hazard3 MCU SoC, including its JTAG DTM, async APB bridge, debug
// module, CPU, arbitration and AHB SRAM. The test copies mcu_top into its
// build directory with the HPM test alias translated only at the SBA port.
module jtag200_hazard_target(
    input wire resetn, tck, tms, tdi,
    output wire tdo
);
    reg clock = 0;
    always #6.25 clock = !clock; // 80 MHz, independent of sender and JTAG.
    wire target_tdo;
    assign #0.8 tdo = target_tdo;
    wire [31:0] gpio_out,gpio_oe;
    mcu_top dut(
        .clk(clock), .resetn(resetn), .jtag_tck(tck), .jtag_trstn(resetn),
        .jtag_tms(tms), .jtag_tdi(tdi), .jtag_tdo(target_tdo),
        .uart_rx(1'b1), .gpio_in(32'b0), .gpio_out(gpio_out), .gpio_oe(gpio_oe),
        .spi_miso(1'b0)
    );
    initial begin
        for (integer address=0; address<32768; address=address+1)
            dut.u_memory.mem[address] = 0;
        dut.u_memory.mem[0] = 32'h0000006f; // jal x0,0, running throughout SBA.
    end
endmodule
