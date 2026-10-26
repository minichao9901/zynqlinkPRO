`timescale 1ns/1ps
module swd_batch_engine #(
    parameter BRAM_ADDR_W = 10
)(
    input  wire                   clk,
    input  wire                   rst_n,

    input  wire                   host_wr_en,
    input  wire                   host_rd_en,
    input  wire [1:0]             host_addr,
    input  wire [31:0]            host_wdata,
    input  wire [3:0]             host_wstrb,
    output wire [31:0]            host_rdata,

    input wire  cmd_bram_en,
    input wire [3:0] cmd_bram_we,
    input wire [31:0] cmd_bram_addr,
    input wire [31:0] cmd_bram_wrdata,
    output wire [31:0] cmd_bram_rddata,
    input wire  rsp_bram_en,
    input wire [3:0] rsp_bram_we,
    input wire [31:0] rsp_bram_addr,
    input wire [31:0] rsp_bram_wrdata,
    output wire [31:0] rsp_bram_rddata,

    output wire                   active,
    output reg                    core_start,
    output reg                    core_mode,
    output reg  [255:0]           core_swj_data,
    output reg  [7:0]             core_swj_count,
    output reg  [7:0]             core_req,
    output reg  [31:0]            core_wdata,
    input  wire                   core_busy,
    input  wire [2:0]             core_ack,
    input  wire                   core_parity_err,
    input  wire [31:0]            core_rdata,
    input  wire                   packet_active,
    input  wire                   packet_cmd_en,
    input  wire [BRAM_ADDR_W-1:0] packet_cmd_addr,
    output wire [31:0]            packet_cmd_data,
    input  wire                   packet_rsp_en,
    input  wire [3:0]             packet_rsp_we,
    input  wire [BRAM_ADDR_W-1:0] packet_rsp_addr,
    input  wire [31:0]            packet_rsp_data
);
    localparam [1:0] HOST_CTRL   = 2'd0;
    localparam [1:0] HOST_STATUS = 2'd1;
    localparam [1:0] HOST_ADDR   = 2'd2;
    localparam [1:0] HOST_DATA   = 2'd3;

    localparam [7:0] CMD_REPEAT_READ = 8'h04;
    localparam [7:0] CMD_REPEAT_WRITE = 8'h05;
    reg [15:0] repeat_left;
    reg repeat_write;
    localparam [5:0] ST_REPEAT_NEXT = 6'd31;

    localparam [7:0] CMD_END             = 8'h00;
    localparam [7:0] CMD_SWJ             = 8'h01;
    localparam [7:0] CMD_XFER_WRITE      = 8'h02;
    localparam [7:0] CMD_XFER_READ       = 8'h03;
    localparam [7:0] CMD_MEM_WRITE_BURST = 8'h20;
    localparam [7:0] CMD_MEM_READ_BURST  = 8'h21;

    localparam [31:0] MEM_AP_SELECT_DP0 = 32'h0000_0000;
    localparam [31:0] MEM_AP_CSW_INC32  = 32'h2300_0012;

    localparam [5:0] ST_IDLE               = 6'd0;
    localparam [5:0] ST_FETCH_HDR          = 6'd1;
    localparam [5:0] ST_FETCH_HDR_D        = 6'd2;
    localparam [5:0] ST_FETCH_HDR_Q        = 6'd3;
    localparam [5:0] ST_DECODE             = 6'd4;
    localparam [5:0] ST_FETCH_WORD         = 6'd5;
    localparam [5:0] ST_FETCH_WORD_D       = 6'd6;
    localparam [5:0] ST_FETCH_WORD_Q       = 6'd7;
    localparam [5:0] ST_SWJ_FETCH          = 6'd8;
    localparam [5:0] ST_SWJ_FETCH_D        = 6'd9;
    localparam [5:0] ST_SWJ_FETCH_Q        = 6'd10;
    localparam [5:0] ST_SWJ_START          = 6'd11;
    localparam [5:0] ST_SWJ_WAIT           = 6'd12;
    localparam [5:0] ST_RAW_START          = 6'd13;
    localparam [5:0] ST_RAW_WAIT           = 6'd14;
    localparam [5:0] ST_XFER_WRITE_GOTDATA = 6'd15;
    localparam [5:0] ST_XFER_READ_STORE    = 6'd16;
    localparam [5:0] ST_MEM_WR_GOT_ADDR    = 6'd17;
    localparam [5:0] ST_MEM_WR_SEL         = 6'd18;
    localparam [5:0] ST_MEM_WR_CSW         = 6'd19;
    localparam [5:0] ST_MEM_WR_TAR         = 6'd20;
    localparam [5:0] ST_MEM_WR_GOT_DATA    = 6'd21;
    localparam [5:0] ST_MEM_WR_AFTER       = 6'd22;
    localparam [5:0] ST_MEM_RD_GOT_ADDR    = 6'd23;
    localparam [5:0] ST_MEM_RD_SEL         = 6'd24;
    localparam [5:0] ST_MEM_RD_CSW         = 6'd25;
    localparam [5:0] ST_MEM_RD_TAR         = 6'd26;
    localparam [5:0] ST_MEM_RD_AFTER_POST0 = 6'd27;
    localparam [5:0] ST_MEM_RD_AFTER_POST1 = 6'd28;
    localparam [5:0] ST_MEM_RD_STORE_POST  = 6'd29;
    localparam [5:0] ST_MEM_RD_STORE_LAST  = 6'd30;

    reg                  done_reg, error_reg;
    reg  [2:0]           last_ack_reg;
    reg  [7:0]           retry_max_reg;
    reg                  bram_sel_reg;
    reg  [BRAM_ADDR_W-1:0] bram_addr_reg;
    reg  [15:0]          rsp_count_reg;

    reg  [5:0]           state, return_state, fetch_return_state;
    reg  [7:0]           opcode_reg;
    reg  [31:0]          hdr_reg, word0_reg, base_addr_reg;
    reg  [15:0]          cmd_pc_reg, rsp_pc_reg, count_reg, index_reg;
    reg                  seen_busy_reg;
    reg  [7:0]           retry_left_reg;

    reg                  cmd_en_b;
    reg  [BRAM_ADDR_W-1:0] cmd_addr_b;
    reg                  rsp_en_b;
    reg  [3:0]           rsp_web_b;
    reg  [BRAM_ADDR_W-1:0] rsp_addr_b;
    reg  [31:0]          rsp_din_b;

    wire                 axibram_wr;
    wire [3:0]           cmd_wea;
    wire [3:0]           rsp_wea;
    wire [31:0]          cmd_douta, cmd_doutb, rsp_douta, rsp_doutb;
    assign packet_cmd_data = cmd_doutb;

    assign axibram_wr = host_wr_en && (host_addr == HOST_DATA);
    assign cmd_bram_rddata = cmd_douta;
    assign rsp_bram_rddata = rsp_douta;
    assign cmd_wea    = cmd_bram_en ? cmd_bram_we : (axibram_wr && !bram_sel_reg) ? host_wstrb : 4'b0000;
    assign rsp_wea    = rsp_bram_en ? rsp_bram_we : (axibram_wr &&  bram_sel_reg) ? host_wstrb : 4'b0000;
    assign active     = (state != ST_IDLE);

    xpm_memory_tdpram #(
        .ADDR_WIDTH_A(BRAM_ADDR_W), .ADDR_WIDTH_B(BRAM_ADDR_W),
        .AUTO_SLEEP_TIME(0), .BYTE_WRITE_WIDTH_A(8), .BYTE_WRITE_WIDTH_B(8),
        .CLOCKING_MODE("common_clock"), .MEMORY_INIT_FILE("none"),
        .MEMORY_INIT_PARAM("0"), .MEMORY_OPTIMIZATION("true"),
        .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE((1 << BRAM_ADDR_W) * 32),
        .MESSAGE_CONTROL(0), .READ_DATA_WIDTH_A(32), .READ_DATA_WIDTH_B(32),
        .READ_LATENCY_A(1), .READ_LATENCY_B(1), .READ_RESET_VALUE_A("0"),
        .READ_RESET_VALUE_B("0"), .RST_MODE_A("SYNC"), .RST_MODE_B("SYNC"),
        .USE_MEM_INIT(0), .WAKEUP_TIME("disable_sleep"),
        .WRITE_DATA_WIDTH_A(32), .WRITE_DATA_WIDTH_B(32),
        .WRITE_MODE_A("read_first"), .WRITE_MODE_B("read_first")
    ) u_cmd_bram (
        .clka(clk), .ena(1'b1), .wea(cmd_wea), .addra(cmd_bram_en ? cmd_bram_addr[BRAM_ADDR_W+1:2] : bram_addr_reg), .dina(cmd_bram_en ? cmd_bram_wrdata : host_wdata), .douta(cmd_douta),
        .rsta(1'b0), .regcea(1'b1),
        .clkb(clk), .enb(packet_active ? packet_cmd_en : cmd_en_b), .web(4'b0000),
        .addrb(packet_active ? packet_cmd_addr : cmd_addr_b), .dinb(32'd0), .doutb(cmd_doutb),
        .rstb(1'b0), .regceb(1'b1)
    );

    xpm_memory_tdpram #(
        .ADDR_WIDTH_A(BRAM_ADDR_W), .ADDR_WIDTH_B(BRAM_ADDR_W),
        .AUTO_SLEEP_TIME(0), .BYTE_WRITE_WIDTH_A(8), .BYTE_WRITE_WIDTH_B(8),
        .CLOCKING_MODE("common_clock"), .MEMORY_INIT_FILE("none"),
        .MEMORY_INIT_PARAM("0"), .MEMORY_OPTIMIZATION("true"),
        .MEMORY_PRIMITIVE("block"), .MEMORY_SIZE((1 << BRAM_ADDR_W) * 32),
        .MESSAGE_CONTROL(0), .READ_DATA_WIDTH_A(32), .READ_DATA_WIDTH_B(32),
        .READ_LATENCY_A(1), .READ_LATENCY_B(1), .READ_RESET_VALUE_A("0"),
        .READ_RESET_VALUE_B("0"), .RST_MODE_A("SYNC"), .RST_MODE_B("SYNC"),
        .USE_MEM_INIT(0), .WAKEUP_TIME("disable_sleep"),
        .WRITE_DATA_WIDTH_A(32), .WRITE_DATA_WIDTH_B(32),
        .WRITE_MODE_A("read_first"), .WRITE_MODE_B("read_first")
    ) u_rsp_bram (
        .clka(clk), .ena(1'b1), .wea(rsp_wea), .addra(rsp_bram_en ? rsp_bram_addr[BRAM_ADDR_W+1:2] : bram_addr_reg), .dina(rsp_bram_en ? rsp_bram_wrdata : host_wdata), .douta(rsp_douta),
        .rsta(1'b0), .regcea(1'b1),
        .clkb(clk), .enb(packet_active ? packet_rsp_en : rsp_en_b),
        .web(packet_active ? packet_rsp_we : rsp_web_b),
        .addrb(packet_active ? packet_rsp_addr : rsp_addr_b),
        .dinb(packet_active ? packet_rsp_data : rsp_din_b), .doutb(rsp_doutb),
        .rstb(1'b0), .regceb(1'b1)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin

            done_reg <= 1'b0;
            error_reg <= 1'b0;
            last_ack_reg <= 3'b000;
            retry_max_reg <= 8'd16;
            bram_sel_reg <= 1'b0;
            bram_addr_reg <= {BRAM_ADDR_W{1'b0}};
            rsp_count_reg <= 16'd0;
            repeat_left <= 0;
            repeat_write <= 0;
            state <= ST_IDLE;
            return_state <= ST_IDLE;
            fetch_return_state <= ST_IDLE;
            opcode_reg <= CMD_END;
            hdr_reg <= 32'd0;
            word0_reg <= 32'd0;
            base_addr_reg <= 32'd0;
            cmd_pc_reg <= 16'd0;
            rsp_pc_reg <= 16'd0;
            count_reg <= 16'd0;
            index_reg <= 16'd0;
            seen_busy_reg <= 1'b0;
            retry_left_reg <= 8'd0;
            core_start <= 1'b0;
            core_mode <= 1'b0;
            core_swj_data <= 256'd0;
            core_swj_count <= 8'd0;
            core_req <= 8'd0;
            core_wdata <= 32'd0;
            cmd_en_b <= 1'b0;
            cmd_addr_b <= {BRAM_ADDR_W{1'b0}};
            rsp_en_b <= 1'b0;
            rsp_web_b <= 4'b0000;
            rsp_addr_b <= {BRAM_ADDR_W{1'b0}};
            rsp_din_b <= 32'd0;
        end else begin
            core_start <= 1'b0;
            // Pre-arm another identical read while the current read is
            // completing. The core accepts only in IDLE; WAIT/parity errors
            // withdraw this level before that edge.
            if (state == ST_RAW_WAIT && seen_busy_reg && core_busy &&
                core_ack == 3'b001 && !core_parity_err &&
                return_state == ST_XFER_READ_STORE && repeat_left != 0)
                core_start <= 1'b1;

            cmd_en_b <= 1'b0;
            rsp_en_b <= 1'b0;
            rsp_web_b <= 4'b0000;

            if (host_wr_en) begin
                case (host_addr)
                    HOST_CTRL: begin
                        retry_max_reg <= host_wdata[15:8];
                        if (host_wdata[1]) begin
                            done_reg <= 1'b0;
                            error_reg <= 1'b0;
                            last_ack_reg <= 3'b000;
                            rsp_count_reg <= 16'd0;
                        end
                        if (host_wdata[0] && (state == ST_IDLE) && !core_busy) begin

                            done_reg <= 1'b0;
                            error_reg <= 1'b0;
                            last_ack_reg <= 3'b000;
                            rsp_count_reg <= 16'd0;
                            cmd_pc_reg <= 16'd0;
                            rsp_pc_reg <= 16'd0;
                            count_reg <= 16'd0;
                            index_reg <= 16'd0;
                            state <= ST_FETCH_HDR;
                        end
                    end
                    HOST_ADDR: begin
                        bram_sel_reg <= host_wdata[16];
                        bram_addr_reg <= host_wdata[BRAM_ADDR_W-1:0];
                    end
                    HOST_DATA: begin
                        bram_addr_reg <= bram_addr_reg + 1'b1;
                    end
                    default: ;
                endcase
            end

            if (host_rd_en && (host_addr == HOST_DATA)) begin
                bram_addr_reg <= bram_addr_reg + 1'b1;
            end

            case (state)
                ST_IDLE: begin

                end
                ST_FETCH_HDR: begin
                    cmd_en_b <= 1'b1;
                    cmd_addr_b <= cmd_pc_reg[BRAM_ADDR_W-1:0];
                    state <= ST_FETCH_HDR_D;
                end
                ST_FETCH_HDR_D: begin
                    state <= ST_FETCH_HDR_Q;
                end
                ST_FETCH_HDR_Q: begin
                    hdr_reg <= cmd_doutb;
                    opcode_reg <= cmd_doutb[31:24];
                    cmd_pc_reg <= cmd_pc_reg + 1'b1;
                    state <= ST_DECODE;
                end
                ST_DECODE: begin
                    repeat_left <= 0;
                    repeat_write <= 0;
                    case (opcode_reg)
                        CMD_END: begin

                            done_reg <= 1'b1;
                            state <= ST_IDLE;
                        end
                        CMD_SWJ: begin
                            core_swj_count <= hdr_reg[7:0];
                            count_reg <= (hdr_reg[15:0] + 16'd31) >> 5;
                            index_reg <= 16'd0;
                            core_swj_data <= 256'd0;
                            if (hdr_reg[15:0] > 16'd255) begin

                                done_reg <= 1'b1;
                                error_reg <= 1'b1;
                                state <= ST_IDLE;
                            end else begin
                                state <= ST_SWJ_FETCH;
                            end
                        end
                        CMD_REPEAT_READ, CMD_REPEAT_WRITE: begin
                            // [31:24] opcode, [23:8] count, [7:0] raw SWD request.
                            // Write words immediately follow this one header.
                            core_req <= hdr_reg[7:0];
                            repeat_left <= hdr_reg[23:8];
                            repeat_write <= (opcode_reg == CMD_REPEAT_WRITE);
                            state <= ST_REPEAT_NEXT;
                        end
                        CMD_XFER_WRITE: begin
                            core_req <= hdr_reg[7:0];
                            fetch_return_state <= ST_XFER_WRITE_GOTDATA;
                            state <= ST_FETCH_WORD;
                        end
                        CMD_XFER_READ: begin
                            core_req <= hdr_reg[7:0];
                            retry_left_reg <= retry_max_reg;
                            return_state <= ST_XFER_READ_STORE;
                            state <= ST_RAW_START;
                        end
                        CMD_MEM_WRITE_BURST: begin
                            count_reg <= hdr_reg[15:0];
                            if (hdr_reg[15:0] == 16'd0) begin
                                state <= ST_FETCH_HDR;
                            end else begin
                                fetch_return_state <= ST_MEM_WR_GOT_ADDR;
                                state <= ST_FETCH_WORD;
                            end
                        end
                        CMD_MEM_READ_BURST: begin
                            count_reg <= hdr_reg[15:0];
                            if (hdr_reg[15:0] == 16'd0) begin
                                state <= ST_FETCH_HDR;
                            end else begin
                                fetch_return_state <= ST_MEM_RD_GOT_ADDR;
                                state <= ST_FETCH_WORD;
                            end
                        end
                        default: begin

                            done_reg <= 1'b1;
                            error_reg <= 1'b1;
                            state <= ST_IDLE;
                        end
                    endcase
                end
                ST_FETCH_WORD: begin
                    cmd_en_b <= 1'b1;
                    cmd_addr_b <= cmd_pc_reg[BRAM_ADDR_W-1:0];
                    state <= ST_FETCH_WORD_D;
                end
                ST_FETCH_WORD_D: begin
                    state <= ST_FETCH_WORD_Q;
                end
                ST_FETCH_WORD_Q: begin
                    word0_reg <= cmd_doutb;
                    cmd_pc_reg <= cmd_pc_reg + 1'b1;
                    state <= fetch_return_state;
                end
                ST_SWJ_FETCH: begin
                    if (index_reg < count_reg) begin
                        cmd_en_b <= 1'b1;
                        cmd_addr_b <= cmd_pc_reg[BRAM_ADDR_W-1:0];
                        state <= ST_SWJ_FETCH_D;
                    end else begin
                        state <= ST_SWJ_START;
                    end
                end
                ST_SWJ_FETCH_D: begin
                    state <= ST_SWJ_FETCH_Q;
                end
                ST_SWJ_FETCH_Q: begin
                    core_swj_data[(index_reg*32) +: 32] <= cmd_doutb;
                    cmd_pc_reg <= cmd_pc_reg + 1'b1;
                    index_reg <= index_reg + 1'b1;
                    state <= ST_SWJ_FETCH;
                end
                ST_SWJ_START: begin
                    core_mode <= 1'b0;
                    core_start <= 1'b1;
                    seen_busy_reg <= 1'b0;
                    state <= ST_SWJ_WAIT;
                end
                ST_SWJ_WAIT: begin
                    if (core_busy) begin
                        seen_busy_reg <= 1'b1;
                    end else if (seen_busy_reg) begin
                        state <= ST_FETCH_HDR;
                    end
                end
                ST_REPEAT_NEXT: begin
                    if (repeat_left == 0) begin
                        state <= ST_FETCH_HDR;
                    end else begin
                        repeat_left <= repeat_left - 1'b1;
                        if (repeat_write) begin
                            fetch_return_state <= ST_XFER_WRITE_GOTDATA;
                            state <= ST_FETCH_WORD;
                        end else begin
                            retry_left_reg <= retry_max_reg;
                            return_state <= ST_XFER_READ_STORE;
                            state <= ST_RAW_START;
                        end
                    end
                end
                ST_XFER_WRITE_GOTDATA: begin
                    core_wdata <= word0_reg;
                    retry_left_reg <= retry_max_reg;
                    return_state <= repeat_write ? ST_REPEAT_NEXT : ST_FETCH_HDR;
                    state <= ST_RAW_START;
                end
                ST_XFER_READ_STORE: begin
                    rsp_en_b <= 1'b1;
                    rsp_web_b <= 4'hF;
                    rsp_addr_b <= rsp_pc_reg[BRAM_ADDR_W-1:0];
                    rsp_din_b <= core_rdata;
                    rsp_pc_reg <= rsp_pc_reg + 1'b1;
                    rsp_count_reg <= rsp_count_reg + 1'b1;
                    state <= (repeat_left != 0) ? ST_REPEAT_NEXT : ST_FETCH_HDR;
                end
                ST_MEM_WR_GOT_ADDR: begin
                    base_addr_reg <= word0_reg;
                    core_req <= 8'h08;
                    core_wdata <= MEM_AP_SELECT_DP0;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_WR_SEL;
                    state <= ST_RAW_START;
                end
                ST_MEM_WR_SEL: begin
                    core_req <= 8'h01;
                    core_wdata <= MEM_AP_CSW_INC32;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_WR_CSW;
                    state <= ST_RAW_START;
                end
                ST_MEM_WR_CSW: begin
                    core_req <= 8'h05;
                    core_wdata <= base_addr_reg;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_WR_TAR;
                    state <= ST_RAW_START;
                end
                ST_MEM_WR_TAR: begin
                    fetch_return_state <= ST_MEM_WR_GOT_DATA;
                    state <= ST_FETCH_WORD;
                end
                ST_MEM_WR_GOT_DATA: begin
                    core_req <= 8'h0D;
                    core_wdata <= word0_reg;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_WR_AFTER;
                    state <= ST_RAW_START;
                end
                ST_MEM_WR_AFTER: begin
                    if (count_reg <= 16'd1) begin
                        count_reg <= 16'd0;
                        state <= ST_FETCH_HDR;
                    end else begin
                        count_reg <= count_reg - 1'b1;
                        fetch_return_state <= ST_MEM_WR_GOT_DATA;
                        state <= ST_FETCH_WORD;
                    end
                end
                ST_MEM_RD_GOT_ADDR: begin
                    base_addr_reg <= word0_reg;
                    core_req <= 8'h08;
                    core_wdata <= MEM_AP_SELECT_DP0;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_RD_SEL;
                    state <= ST_RAW_START;
                end
                ST_MEM_RD_SEL: begin
                    core_req <= 8'h01;
                    core_wdata <= MEM_AP_CSW_INC32;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_RD_CSW;
                    state <= ST_RAW_START;
                end
                ST_MEM_RD_CSW: begin
                    core_req <= 8'h05;
                    core_wdata <= base_addr_reg;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_RD_TAR;
                    state <= ST_RAW_START;
                end
                ST_MEM_RD_TAR: begin
                    core_req <= 8'h0F;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_RD_AFTER_POST0;
                    state <= ST_RAW_START;
                end
                ST_MEM_RD_AFTER_POST0: begin
                    core_req <= 8'h0F;
                    retry_left_reg <= retry_max_reg;
                    return_state <= ST_MEM_RD_AFTER_POST1;
                    state <= ST_RAW_START;
                end
                ST_MEM_RD_AFTER_POST1: begin
                    if (count_reg == 16'd1) begin
                        core_req <= 8'h0E;
                        retry_left_reg <= retry_max_reg;
                        return_state <= ST_MEM_RD_STORE_LAST;
                        state <= ST_RAW_START;
                    end else begin
                        core_req <= 8'h0F;
                        retry_left_reg <= retry_max_reg;
                        return_state <= ST_MEM_RD_STORE_POST;
                        state <= ST_RAW_START;
                    end
                end
                ST_MEM_RD_STORE_POST: begin
                    rsp_en_b <= 1'b1;
                    rsp_web_b <= 4'hF;
                    rsp_addr_b <= rsp_pc_reg[BRAM_ADDR_W-1:0];
                    rsp_din_b <= core_rdata;
                    rsp_pc_reg <= rsp_pc_reg + 1'b1;
                    rsp_count_reg <= rsp_count_reg + 1'b1;
                    count_reg <= count_reg - 1'b1;
                    if (count_reg == 16'd2) begin
                        core_req <= 8'h0E;
                        retry_left_reg <= retry_max_reg;
                        return_state <= ST_MEM_RD_STORE_LAST;
                        state <= ST_RAW_START;
                    end else begin
                        core_req <= 8'h0F;
                        retry_left_reg <= retry_max_reg;
                        return_state <= ST_MEM_RD_STORE_POST;
                        state <= ST_RAW_START;
                    end
                end
                ST_MEM_RD_STORE_LAST: begin
                    rsp_en_b <= 1'b1;
                    rsp_web_b <= 4'hF;
                    rsp_addr_b <= rsp_pc_reg[BRAM_ADDR_W-1:0];
                    rsp_din_b <= core_rdata;
                    rsp_pc_reg <= rsp_pc_reg + 1'b1;
                    rsp_count_reg <= rsp_count_reg + 1'b1;
                    count_reg <= 16'd0;
                    state <= ST_FETCH_HDR;
                end
                ST_RAW_START: begin
                    core_mode <= 1'b1;
                    core_start <= 1'b1;
                    seen_busy_reg <= 1'b0;
                    state <= ST_RAW_WAIT;
                end
                ST_RAW_WAIT: begin
                    if (core_busy) begin
                        seen_busy_reg <= 1'b1;
                    end else if (seen_busy_reg) begin
                        last_ack_reg <= core_ack;
                        if ((core_ack == 3'b010) && (retry_left_reg != 0)) begin
                            retry_left_reg <= retry_left_reg - 1'b1;
                            state <= ST_RAW_START;
                        end else if (core_ack != 3'b001 || core_parity_err) begin
                            if (core_parity_err) last_ack_reg <= 0;

                            done_reg <= 1'b1;
                            error_reg <= 1'b1;
                            state <= ST_IDLE;
                        end else if (return_state == ST_XFER_READ_STORE && repeat_left != 0) begin
                            // Store and restart in the completion beat,
                            // bypassing STORE -> REPEAT_NEXT -> RAW_START.
                            rsp_en_b <= 1;
                            rsp_web_b <= 4'hF;
                            rsp_addr_b <= rsp_pc_reg[BRAM_ADDR_W-1:0];
                            rsp_din_b <= core_rdata;
                            rsp_pc_reg <= rsp_pc_reg + 1'b1;
                            rsp_count_reg <= rsp_count_reg + 1'b1;
                            repeat_left <= repeat_left - 1'b1;
                            retry_left_reg <= retry_max_reg;
                            seen_busy_reg <= 0;
                            core_start <= 1;
                            state <= ST_RAW_WAIT;
                        end else begin
                            state <= return_state;
                        end
                    end
                end
                default: begin

                    done_reg <= 1'b1;
                    error_reg <= 1'b1;
                    state <= ST_IDLE;
                end
            endcase
        end
    end

    assign host_rdata = (host_addr == HOST_CTRL)   ? {16'd0, retry_max_reg, 6'd0, done_reg, 1'b0} :
                        (host_addr == HOST_STATUS) ? {2'd0, rsp_count_reg, retry_max_reg, last_ack_reg, error_reg, done_reg, active} :
                        (host_addr == HOST_ADDR)   ? {15'd0, bram_sel_reg, 6'd0, bram_addr_reg} :
                        (host_addr == HOST_DATA)   ? (bram_sel_reg ? rsp_douta : cmd_douta) :
                                                     32'd0;
endmodule
