`timescale 1ns/1ps
module tb_swd_sequence_pins;
    reg clk=0;
    always #5 clk=~clk;
    reg rst_n=0;
    reg [7:0] awaddr=0, araddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0, wvalid=0, arvalid=0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [31:0] rdata;
    tri swdio;
    wire swclk;
    tri [3:0] gpio;
    reg target_enable=0, target_bit=0, target_tdo=1;
    assign swdio=target_enable ? target_bit : 1'bz;
    assign gpio[1]=target_tdo;
    swd_controller #(.ENABLE_DIAGNOSTICS(0)) dut(
        .clk(clk),.rst_n(rst_n),.s_axi_awaddr(awaddr),.s_axi_awprot(3'd0),
        .s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),
        .s_axi_wstrb(4'hf),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(1'b1),.s_axi_araddr(araddr),
        .s_axi_arprot(3'd0),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(1'b1),
        .cmd_bram_clk(clk),.cmd_bram_rst(1'b0),.cmd_bram_en(1'b0),.cmd_bram_we(4'd0),
        .cmd_bram_addr(32'd0),.cmd_bram_wrdata(32'd0),
        .rsp_bram_clk(clk),.rsp_bram_rst(1'b0),.rsp_bram_en(1'b0),.rsp_bram_we(4'd0),
        .rsp_bram_addr(32'd0),.rsp_bram_wrdata(32'd0),
        .pkt_bram_clk(clk),.pkt_bram_rst(1'b0),.pkt_bram_en(1'b0),.pkt_bram_we(4'd0),
        .pkt_bram_addr(32'd0),.pkt_bram_wrdata(32'd0),
        .gpio_aux(gpio),.gpio_out(4'd0),.gpio_tri(4'd0),.swclk(swclk),.swdio(swdio));

    task wr(input [7:0] address,input [31:0] value);
        @(negedge clk); awaddr=address; wdata=value; awvalid=1; wvalid=1;
        @(posedge clk); while(!(awready && wready)) @(posedge clk);
        @(negedge clk); awvalid=0; wvalid=0;
        wait(bvalid); repeat(2) @(negedge clk);
    endtask
    task rd(input [7:0] address,output [31:0] value);
        @(negedge clk); araddr=address; arvalid=1;
        @(posedge clk); while(!arready) @(posedge clk);
        @(negedge clk); arvalid=0;
        wait(rvalid); value=rdata; @(negedge clk);
    endtask
    reg [31:0] value;
    integer route, bitvalue;
    initial begin
        repeat(3) @(negedge clk); rst_n=1;
        rd(8'h4c,value);
        if(value!==32'h4450007f) $fatal(1,"Missing manual direction feature");
        for(route=2; route<=3; route=route+1) begin
            wr(8'h80,route);
            for(bitvalue=0; bitvalue<2; bitvalue=bitvalue+1) begin
                target_tdo=bitvalue;
                wr(8'h94,32'h100|(2*(1-bitvalue)));
                if(swdio!==1-bitvalue || gpio[1]!==bitvalue || dut.g_aux[1].pin_t!==1)
                    $fatal(1,"Manual output or TDO isolation route=%d",route);
            end
            wr(8'h94,32'h300);
            if(swdio!==1'bz) $fatal(1,"SWDIO not released");
            target_enable=1;
            for(bitvalue=0; bitvalue<2; bitvalue=bitvalue+1) begin
                target_bit=bitvalue;
                wr(8'h94,32'h301);
                rd(8'h94,value);
                if(!value[9] || !value[8] || value[1]!==bitvalue || swclk!==1)
                    $fatal(1,"Manual input direction/readback lost");
            end
            target_enable=0;
            wr(8'h94,32'h102);
            if(swdio!==1'b1 || dut.u_swdio_iobuf.T!==0) $fatal(1,"Output direction not restored");
        end
        wr(8'h80,0);
        if(swdio!==1'bz) $fatal(1,"Disconnected SWDIO still driven");
        $display("PASS manual SWDIO output/input/readback and permanent TDO isolation in SWD/JTAG");
        $finish;
    end
    initial begin #100000; $fatal(1,"Timeout"); end
endmodule

module IOBUF(input I,T,inout IO,output O);
    assign IO=T?1'bz:I;
    assign O=IO;
endmodule
module IDDR #(parameter DDR_CLK_EDGE="OPPOSITE_EDGE",INIT_Q1=0,INIT_Q2=0,SRTYPE="SYNC")
    (input C,CE,D,R,S,output reg Q1,Q2);
    always @(posedge C) if(CE) Q1<=D;
    always @(negedge C) if(CE) Q2<=D;
endmodule
