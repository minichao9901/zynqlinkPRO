`timescale 1ns/1ps
// AXI4-Lite register bank and dual-clock waveform buffers for the PS.
module jtag200_regs (
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET axi_aresetn" *)
    input wire axi_aclk,
    input wire axi_aresetn,
    input wire [13:0] s_axi_awaddr,
    input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    input wire [13:0] s_axi_araddr,
    input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    output reg phy_hold = 1,
    input wire ready,
    input wire delay_ready,
    output reg delay_load = 0,
    output reg [4:0] delay_value = 0,
    input wire word_clk,
    input wire word_reset,
    output wire [23:0] lane_word,
    input wire [7:0] rx_word
);
    reg [13:0] write_addr;
    reg [31:0] write_data;
    reg [3:0] write_strobes;
    reg have_addr = 0, have_data = 0;
    reg reading_rx = 0;
    reg run = 0;
    wire done, rx_write;
    (* ASYNC_REG = "TRUE" *) reg [1:0] ready_sync = 0, done_sync = 0, delay_sync = 0;
    wire [8:0] tx_addr, rx_addr;
    reg [24:0] tx_word;
    reg [7:0] rx_read;
    (* ram_style = "block" *) reg [24:0] tx_mem [0:511];
    (* ram_style = "block" *) reg [7:0] rx_mem [0:511];

    wire write_pending = have_addr && have_data && !s_axi_bvalid;
    wire control_write = write_strobes == 4'hf && write_addr[1:0] == 0;
    wire write_tx = write_pending && control_write && write_addr[13:11] == 3'b010 && !run && !done_sync[1];
    wire valid_read = s_axi_arvalid && s_axi_arready && s_axi_araddr[1:0] == 0;
    wire read_rx = valid_read && s_axi_araddr[13:11] == 3'b100 && done_sync[1];

    assign s_axi_awready = !have_addr && !s_axi_bvalid;
    assign s_axi_wready = !have_data && !s_axi_bvalid;
    assign s_axi_arready = !reading_rx && !s_axi_rvalid;

    always @(posedge word_clk) begin
        tx_word <= tx_mem[tx_addr];
        if (rx_write) rx_mem[rx_addr] <= rx_word;
    end
    always @(posedge axi_aclk) begin
        if (write_tx) tx_mem[write_addr[10:2]] <= write_data[24:0];
        if (read_rx) rx_read <= rx_mem[s_axi_araddr[10:2]];
    end

    jtag200_wave wave (
        .clk(word_clk), .reset(word_reset), .run(run),
        .done(done), .tx_addr(tx_addr), .rx_addr(rx_addr), .rx_write(rx_write),
        .tx_word(tx_word), .lane_word(lane_word)
    );

    always @(posedge axi_aclk) begin
        if (!axi_aresetn) begin
            have_addr <= 0;
            have_data <= 0;
            s_axi_rvalid <= 0;
            s_axi_bvalid <= 0;
            reading_rx <= 0;
            phy_hold <= 1;
            delay_load <= 0;
            delay_value <= 0;
            run <= 0;
            ready_sync <= 0;
            done_sync <= 0;
            delay_sync <= 0;
        end else begin
            ready_sync <= {ready_sync[0], ready};
            done_sync <= {done_sync[0], done};
            delay_sync <= {delay_sync[0], delay_ready};
            delay_load <= 0;
            if (s_axi_awvalid && s_axi_awready) begin
                write_addr <= s_axi_awaddr;
                have_addr <= 1;
            end
            if (s_axi_wvalid && s_axi_wready) begin
                write_data <= s_axi_wdata;
                write_strobes <= s_axi_wstrb;
                have_data <= 1;
            end
            if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            if (write_pending) begin
                have_addr <= 0;
                have_data <= 0;
                s_axi_bvalid <= 1;
                s_axi_bresp <= 2'b10;
                if (write_tx) s_axi_bresp <= 0;
                if (control_write && write_addr == 14'h008) begin
                    // Stop only after the last TCK falling edge and drain.
                    if (!write_data[0] && (!run || done_sync[1])) begin
                        run <= 0;
                        phy_hold <= write_data[1];
                        s_axi_bresp <= 0;
                    end
                    if (write_data[0] && !write_data[1] && !run && !done_sync[1] &&
                        !phy_hold && ready_sync[1] && delay_sync[1]) begin
                        run <= 1;
                        s_axi_bresp <= 0;
                    end
                end
                if (control_write && write_addr == 14'h00c && !run && delay_sync[1]) begin
                    delay_value <= write_data[4:0];
                    delay_load <= 1;
                    s_axi_bresp <= 0;
                end
            end

            if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0;
            if (reading_rx) begin
                reading_rx <= 0;
                s_axi_rdata <= {24'b0, rx_read};
                s_axi_rresp <= 0;
                s_axi_rvalid <= 1;
            end
            if (s_axi_arvalid && s_axi_arready) begin
                if (read_rx) reading_rx <= 1;
                else begin
                    s_axi_rresp <= 0;
                    s_axi_rvalid <= 1;
                    case (s_axi_araddr)
                        14'h000: s_axi_rdata <= 32'h4a323030; // J200
                        14'h004: s_axi_rdata <= {27'b0, phy_hold, run, delay_sync[1], done_sync[1], ready_sync[1]};
                        14'h00c: s_axi_rdata <= {27'b0, delay_value};
                        default: begin
                            s_axi_rdata <= 0;
                            s_axi_rresp <= 2'b10;
                        end
                    endcase
                end
            end
        end
    end
endmodule
