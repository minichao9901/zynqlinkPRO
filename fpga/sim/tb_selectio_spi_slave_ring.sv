`timescale 1ns/1ps
module tb_selectio_spi_slave_ring #(parameter PAD_DIAG=0);
    localparam integer CAPACITY = 65536;
    localparam integer BLOCK = 4096;
    localparam integer LENGTH = CAPACITY + 2*BLOCK - 1;
    reg axi_clk = 0, quad_clk = 0;
    always #3.75 axi_clk = ~axi_clk;
    always #5 quad_clk = ~quad_clk;

    reg reset = 1;
    reg [16:0] awaddr = 0, araddr = 0;
    reg [31:0] wdata = 0;
    reg awvalid = 0, wvalid = 0, arvalid = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;

    reg [3:0] sck = 0, cs_n = 15, mosi = 0;
    wire pad_request, listening;
    selectio_aux_regs #(.SPI_PAD_DIAG(PAD_DIAG)) dut (
        .axi_aclk(axi_clk), .axi_aresetn(!reset),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b0), .s_axi_awvalid(awvalid),
        .s_axi_awready(awready), .s_axi_wdata(wdata), .s_axi_wstrb(4'hf),
        .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(1'b1),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b0), .s_axi_arvalid(arvalid),
        .s_axi_arready(arready), .s_axi_rdata(rdata), .s_axi_rresp(rresp),
        .s_axi_rvalid(rvalid), .s_axi_rready(1'b1),
        .quad_clk(quad_clk), .phy_reset(reset), .pad_granted(pad_request),
        .uart_granted(1'b0), .wide_samples(8'b0), .pad_samples(4'b0),
        .pad_request(pad_request), .uart_request(), .spi_selected(), .monitor_tdi(),
        .clock_slots(), .select_slots(), .tx_slots(),
        .slave_sck(sck), .slave_cs_n(cs_n), .slave_mosi(mosi),
        .spi_slave_selected(listening)
    );

    task automatic write_reg(input [16:0] address, input [31:0] data,
                             input [1:0] expected = 0);
        @(negedge axi_clk);
        awaddr = address;
        wdata = data;
        awvalid = 1;
        wvalid = 1;
        fork
            begin
                do @(posedge axi_clk); while (!awready);
                @(negedge axi_clk);
                awvalid = 0;
            end
            begin
                do @(posedge axi_clk); while (!wready);
                @(negedge axi_clk);
                wvalid = 0;
            end
        join
        do @(posedge axi_clk); while (!bvalid);
        if (bresp !== expected)
            $fatal(1, "write %h response %d expected %d", address, bresp, expected);
    endtask

    task automatic read_reg(input [16:0] address, output [31:0] data);
        @(negedge axi_clk);
        araddr = address;
        arvalid = 1;
        do @(posedge axi_clk); while (!arready);
        @(negedge axi_clk);
        arvalid = 0;
        do @(posedge axi_clk); while (!rvalid);
        if (rresp !== 0) $fatal(1, "read %h response %d", address, rresp);
        data = rdata;
    endtask

    task automatic wait_clear(input [31:0] mask);
        reg [31:0] status;
        do read_reg(17'h04, status); while ((status & mask) != 0);
    endtask

    function automatic [7:0] octet(input integer index);
        octet = index ^ (index >> 3) ^ (index >> 12);
    endfunction

    // Drive the four post-ISERDES samples for every 10 ns SCK period.
    // Mode 0 has one rising edge at sample 1 and a falling edge at sample 3.
    task automatic send(input integer length, input integer partial_bits);
        reg [7:0] data;
        for (integer i = 0; i < length; i = i + 1) begin
            data = octet(i);
            for (integer bit_number = 7; bit_number >= 0; bit_number = bit_number - 1) begin
                @(negedge quad_clk);
                cs_n = 0;
                sck = 4'b0110;
                mosi = {4{data[bit_number]}};
            end
        end
        repeat (partial_bits) begin
            @(negedge quad_clk);
            sck = 4'b0110;
            mosi = 0;
        end
        @(negedge quad_clk);
        cs_n = 15;
        sck = 0;
    endtask

    task automatic drain(input integer total);
        reg [31:0] available, pointer, data;
        integer count, offset, address;
        for (offset = 0; offset < total; offset = offset + count) begin
            count = total - offset;
            if (count > BLOCK) count = BLOCK;
            do begin
                repeat (25) @(posedge axi_clk);
                read_reg(17'h24, available);
            end while (available < count);
            read_reg(17'h20, pointer);
            if (pointer !== offset[16:0])
                $fatal(1, "unexpected consumer pointer %d at %d", pointer, offset);
            for (integer i = 0; i < count; i = i + 4) begin
                address = (pointer + i) & 16'hfffc;
                read_reg(17'h10000 + address, data);
                for (integer lane = 0; lane < 4 && i + lane < count; lane = lane + 1)
                    if (data[8*lane +: 8] !== octet(offset+i+lane))
                        $fatal(1, "byte %d got %h expected %h",
                               offset+i+lane, data[8*lane +: 8], octet(offset+i+lane));
            end
            write_reg(17'h20, count);
            wait_clear(8);
        end
    endtask

    task automatic counters(input [31:0] expected_drops, expected_errors);
        reg [31:0] drops, errors;
        write_reg(17'h28, 1);
        wait_clear(16);
        read_reg(17'h28, drops);
        read_reg(17'h2c, errors);
        if (drops !== expected_drops || errors !== expected_errors)
            $fatal(1, "counters drops=%d errors=%d expected %d/%d",
                   drops, errors, expected_drops, expected_errors);
    endtask

    task automatic arm;
        write_reg(17'h24, 1);
        wait_clear(8);
        write_reg(17'h18, 0);
        write_reg(17'h08, 7);
        wait (listening);
        repeat (8) @(posedge quad_clk);
    endtask

    reg [31:0] available;
    initial begin
        repeat (12) @(negedge axi_clk);
        reset = 0;
        arm();
        write_reg(17'h1c, 1, 2); // Read-only listener cannot start transmission.
        fork
            send(LENGTH, 0);
            drain(LENGTH);
        join
        read_reg(17'h24, available);
        if (available !== 0) $fatal(1, "tail not fully drained: %d", available);
        counters(0, 0);
        if (PAD_DIAG) begin
            read_reg(17'h38, available);
            if (available !== 32'h53504401) $fatal(1, "capture ready marker %h", available);
            read_reg(17'h4000, available);
            if (available !== 32'h060) $fatal(1, "first capture word %h", available);
            read_reg(17'h403c, available);
            if (available !== 32'h06f) $fatal(1, "capture MOSI/SCK packing %h", available);
        end

        write_reg(17'h08, 0);
        arm();
        if (PAD_DIAG) begin
            read_reg(17'h38, available);
            if (available !== 32'h53504400) $fatal(1, "capture did not rearm %h", available);
        end
        send(CAPACITY + 7, 3);
        repeat (12) @(posedge quad_clk);
        read_reg(17'h24, available);
        if (available !== CAPACITY) $fatal(1, "full-ring length %d", available);
        counters(7, 1);
        drain(CAPACITY);
        write_reg(17'h08, 0);
        arm();
        fork
            send(5, 0);
            drain(5);
        join
        counters(0, 0);

        $display("SPI_SLAVE_RING_PASS 100MHz continuous_bytes=%0d wrap=pass tail=pass overflow=7 frame_error=1 rearm=pass",
                 LENGTH);
        $finish;
    end
    initial begin
        #17000000;
        $fatal(1, "SPI slave ring test timeout");
    end
endmodule
