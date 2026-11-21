`timescale 1ns/1ps
// AXI4-Lite register bank and dual-clock waveform buffers for the PS.
module jtag200_regs #(parameter ENABLE_BLOCK=0) (
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
    input wire [7:0] rx_word,
    output wire [9:0] payload_tx_addr,payload_rx_addr, input wire [31:0] payload_tx_data,
    output wire [31:0] payload_rx_data,output wire payload_rx_write
);
    reg [1:0] park=3;
    reg [2:0] payload_config=0;
    reg [13:0] write_addr;
    reg [31:0] write_data;
    reg [3:0] write_strobes;
    reg have_addr = 0, have_data = 0;
    reg reading_rx = 0;
    reg run = 0, raw_request = 0, block_request = 0;
    reg block_mode = 0, block_write = 0, block_invert = 0;
    reg [31:0] block_address = 0;
    reg [8:0] block_count = 0;
    reg [23:0] block_timing = 0;
    wire raw_done, raw_rx_write, block_done;
    wire [8:0] raw_tx_addr, raw_rx_addr, pipeline_tx_addr, pipeline_rx_addr;
    wire [23:0] raw_lanes, pipeline_lanes;
    wire [31:0] block_word, bits_sent, segments, busy_errors, other_errors;
    wire [3:0] block_rx_enable;
    wire [7:0] completion;
    (* ASYNC_REG = "TRUE" *) reg [1:0] block_mode_sync = 0;
    wire [17:0] end_address = {1'b0,block_address[16:0]} + {7'b0,block_count,2'b0};
    wire [10:0] arm_end_address = {1'b0,block_address[9:0]} + {block_count,2'b0};
    wire block_address_valid = block_timing[21] ?
        (block_address[31:10] == (32'h24050000 >> 10) ||
         block_address[31:16] == 16'h2000) && arm_end_address <= 11'h400 :
        block_address[31:17] == 15'h82 && end_address <= 18'h1FFFC;
    wire block_valid = ENABLE_BLOCK && block_address_valid &&
                       block_address[1:0] == 0 && block_count != 0 && block_count <= 9'd256 &&
                       (block_timing[2:0] == 1 || block_timing[2:0] == 2 || block_timing[2:0] == 4) &&
                       (block_timing[20:19] == 0 || block_timing[2:0] == 2) &&
                       block_timing[9:3] >= 16 && block_timing[9:3] <= 63 &&
                       (!block_timing[23] || block_timing[22]) &&
                       (!block_timing[22] || (block_timing[21] &&
                       ((block_timing[2:0] == 4) || (block_timing[2:0] == 2 && block_timing[10]) ||
                        (block_timing[2:0] == 1 && block_timing[11:10] == 1)))) &&
                       (block_timing[21] ? block_timing[18:10] <= 255 : block_timing[18:10] <= 448);
    reg done = 0;
    (* ASYNC_REG = "TRUE" *) reg [1:0] ready_sync = 0, done_sync = 0, delay_sync = 0;
    wire [8:0] tx_addr = block_mode_sync[1] ? pipeline_tx_addr : raw_tx_addr;
    wire [8:0] rx_addr = block_mode_sync[1] ? pipeline_rx_addr : raw_rx_addr;
    wire [31:0] rx_value = block_mode_sync[1] ? block_word : {24'b0,rx_word};
    wire [3:0] rx_enable = block_mode_sync[1] ? block_rx_enable : {4{raw_rx_write}};
    assign payload_tx_addr={payload_config[1:0],pipeline_tx_addr[7:0]-8'd1};
    assign payload_rx_addr={payload_config[1:0],pipeline_rx_addr[7:0]-8'd1};
    assign payload_rx_data=block_word;
    assign payload_rx_write=payload_config[2] && !block_write && (&block_rx_enable) &&
        pipeline_rx_addr!=0 && pipeline_rx_addr<=block_count;
    assign lane_word = block_mode_sync[1] ? pipeline_lanes : raw_lanes;
    reg [31:0] tx_word, rx_read;
    (* ram_style = "block" *) reg [31:0] tx_mem [0:511];
    (* ram_style = "block" *) reg [31:0] rx_mem [0:511];

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
        if (word_reset) begin
            block_mode_sync <= 0;
            done <= 0;
        end else begin
            block_mode_sync <= {block_mode_sync[0], block_mode};
            done <= block_mode_sync[1] ? block_done : raw_done;
        end
        for (integer lane = 0; lane < 4; lane = lane+1)
            if (rx_enable[lane]) rx_mem[rx_addr][8*lane+:8] <= rx_value[8*lane+:8];
    end
    always @(posedge axi_aclk) begin
        if (write_tx) tx_mem[write_addr[10:2]] <= write_data;
        if (read_rx) rx_read <= rx_mem[s_axi_araddr[10:2]];
    end

    jtag200_wave wave (
        .clk(word_clk), .reset(word_reset), .run(raw_request),.park(park),
        .done(raw_done), .tx_addr(raw_tx_addr), .rx_addr(raw_rx_addr), .rx_write(raw_rx_write),
        .tx_word(tx_word[24:0]), .lane_word(raw_lanes)
    );

    generate if (ENABLE_BLOCK) begin: pipeline
        jtag200_block engine(
            .clk(word_clk), .reset(word_reset), .run(block_request),
            .write_block(block_write), .arm_target(block_timing[21]), .address(block_address), .count(block_count),
            .stream_mode(block_timing[22]), .verify_block(block_timing[23]), .invert_pattern(block_invert),
            .idle_cycles(block_timing[18:10]), .half_slots(block_timing[2:0]),
            .sample_offset(block_timing[9:3]), .tx_word(payload_config[2] ? payload_tx_data : tx_word),
            .advance_tms(block_timing[20]), .advance_tdi(block_timing[19]),
            .tx_addr(pipeline_tx_addr), .rx_addr(pipeline_rx_addr), .result_word(block_word),
            .result_enable(block_rx_enable), .rx_word(rx_word), .lane_word(pipeline_lanes),
            .done(block_done), .completion(completion), .bits_sent(bits_sent), .segments(segments),
            .busy_errors(busy_errors), .other_errors(other_errors)
        );
    end else begin: raw_only
        assign {pipeline_tx_addr,pipeline_rx_addr,block_word,block_rx_enable,pipeline_lanes} = 0;
        assign {block_done,completion,bits_sent,segments,busy_errors,other_errors} = 0;
    end endgenerate

    always @(posedge axi_aclk) begin
        if (!axi_aresetn) begin
            have_addr <= 0;
            have_data <= 0;
            s_axi_rvalid <= 0;
            s_axi_bvalid <= 0;
            reading_rx <= 0;
            phy_hold <= 1;park<=3;
            payload_config <= 0;
            delay_load <= 0;
            delay_value <= 0;
            run <= 0;
            raw_request <= 0;
            block_request <= 0;
            block_mode <= 0;
            block_write <= 0;
            block_invert <= 0;
            block_address <= 0;
            block_count <= 0;
            block_timing <= 0;
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
                        raw_request <= 0;
                        block_request <= 0;
                        phy_hold <= write_data[1];
                        s_axi_bresp <= 0;
                    end
                    if (write_data[0] && !write_data[1] && !run && !done_sync[1] &&
                        !phy_hold && ready_sync[1] && delay_sync[1] &&
                        (!write_data[2] || block_valid)) begin
                        block_mode <= write_data[2];
                        block_write <= write_data[3];
                        block_invert <= block_timing[23] && write_data[4];
                        run <= 1;
                        raw_request <= !write_data[2];
                        block_request <= write_data[2];
                        s_axi_bresp <= 0;
                    end
                end
                if (ENABLE_BLOCK && control_write && !run && !done_sync[1]) begin
                    case (write_addr)
                        14'h038: begin park<=write_data[1:0];s_axi_bresp<=0;end
                        14'h034: begin payload_config <= write_data[2:0]; s_axi_bresp <= 0; end
                        14'h014: begin block_address <= write_data; s_axi_bresp <= 0; end
                        14'h018: if (write_data[31:9] == 0) begin block_count <= write_data[8:0]; s_axi_bresp <= 0; end
                        14'h01c: if (write_data[31:24] == 0) begin block_timing <= write_data[23:0]; s_axi_bresp <= 0; end
                        default: ;
                    endcase
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
                s_axi_rdata <= rx_read;
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
                        14'h038: s_axi_rdata<={30'd0,park};
                        14'h034: s_axi_rdata <= {29'd0,payload_config};
                        14'h010: s_axi_rdata <= ENABLE_BLOCK ? 32'h50495045 : 32'b0; // PIPE
                        14'h014: s_axi_rdata <= block_address;
                        14'h018: s_axi_rdata <= {23'b0,block_count};
                        14'h01c: s_axi_rdata <= {8'b0,block_timing};
                        14'h020: s_axi_rdata <= done_sync[1] && block_mode ? {24'b0,completion} : 0;
                        14'h024: s_axi_rdata <= done_sync[1] && block_mode ? bits_sent : 0;
                        14'h028: s_axi_rdata <= done_sync[1] && block_mode ? segments : 0;
                        14'h02c: s_axi_rdata <= done_sync[1] && block_mode ? busy_errors : 0;
                        14'h030: s_axi_rdata <= done_sync[1] && block_mode ? other_errors : 0;
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
