`timescale 1ns/1ps
// Four 4 KiB windows. Each contains four independent 1 KiB payload banks.
// The CDMA port is clocked by FCLK0; each wire engine uses its own word clock.
module selectio_payload_ram #(parameter SELECTIO_SLICE=0)(
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD CLK" *) input wire host_clk,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD RST" *) input wire host_rst,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD EN" *) input wire host_en,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD WE" *) input wire [3:0] host_we,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD ADDR" *) input wire [31:0] host_addr,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD DIN" *) input wire [31:0] host_wdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:bram:1.0 PAYLOAD DOUT" *) output wire [31:0] host_rdata,
    input wire jtag_clk,swd_clk,
    input wire [9:0] jtag_tx_addr,swd_tx_addr,
    output wire [31:0] jtag_tx_data,swd_tx_data,
    input wire jtag_rx_write,swd_rx_write,
    input wire [9:0] jtag_rx_addr,swd_rx_addr,
    input wire [31:0] jtag_rx_data,swd_rx_data
);
    wire [31:0] jread,sread;
    reg select_swd;
    always @(posedge host_clk) if(host_en) select_swd<=host_addr[13];
    assign host_rdata=select_swd ? (SELECTIO_SLICE==1 ? 32'b0 : sread) :
                                    (SELECTIO_SLICE==2 ? 32'b0 : jread);
    selectio_payload_port #(.ENABLED(SELECTIO_SLICE!=2)) jtag(host_clk,host_en&&!host_addr[13],host_we,host_addr[12:2],
        host_wdata,jread,jtag_clk,jtag_tx_addr,jtag_tx_data,jtag_rx_write,jtag_rx_addr,jtag_rx_data);
    selectio_payload_port #(.ENABLED(SELECTIO_SLICE!=1)) swd(host_clk,host_en&&host_addr[13],host_we,host_addr[12:2],
        host_wdata,sread,swd_clk,swd_tx_addr,swd_tx_data,swd_rx_write,swd_rx_addr,swd_rx_data);
endmodule

module selectio_payload_port #(parameter ENABLED=1)(input wire host_clk,en,input wire [3:0] we,input wire [10:0] addr,
    input wire [31:0] wdata,output reg [31:0] rdata,input wire io_clk,input wire [9:0] tx_addr,
    output reg [31:0] tx_data,input wire rx_write,input wire [9:0] rx_addr,input wire [31:0] rx_data);
    (* ram_style="block" *) reg [31:0] tx[0:1023],rx[0:1023];
    always @(posedge host_clk) begin
        if(ENABLED && en && !addr[10]) for(integer i=0;i<4;i=i+1)
            if(we[i]) tx[addr[9:0]][8*i+:8]<=wdata[8*i+:8];
        if(ENABLED && en && addr[10]) rdata<=rx[addr[9:0]];
    end
    always @(posedge io_clk) begin
        tx_data<=tx[tx_addr];
        if(ENABLED && rx_write) rx[rx_addr]<=rx_data;
    end
endmodule
