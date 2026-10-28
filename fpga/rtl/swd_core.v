//-----------------------------------------------------------------------------
// Module: swd_core
// Description:
//   Single-clock SWD core rewritten as a linear sequence machine.
//   No MMCM phase clocks are used. All protocol actions are explicitly
//   scheduled by state + lsm_cnt half-cycle steps.
//-----------------------------------------------------------------------------

`timescale 1ns / 1ps

module swd_core (
    input  wire        clk,
    input  wire        rst_n,

    // Control interface
    input  wire        start,
    input  wire        next_valid,
    input  wire [7:0]  next_request,
    input  wire [31:0] next_wdata,
    output wire        next_ready,
    output wire        result_valid,
    input  wire        mode,           // 0=SWJ, 1=Transfer
    input  wire        timestamp_en,

    // Configuration
    input  wire [3:0]  idle_cycles,
    input  wire        data_phase,
    input  wire [3:0]  clock_delay,
    input  wire [3:0]  delay_fast,
    // Extra transfer half-cycle steps held low before turnaround's rise.
    input  wire [1:0]  turn_extra,
    // 0=legacy pipeline; 1..7=non-overlapping ACK capture with configurable
    // high-phase hold. The next rise is emitted only after bit capture.
    input  wire [2:0]  ack_delay,
    // Standard receive boundary for short return delays. Legacy mode keeps
    // the original extra-bit receive pipeline used at high SWCLK rates.
    input  wire        rx_boundary,

    // SWJ Sequence
    input  wire [255:0] swj_data,
    input  wire [7:0]   swj_count,

    // Transfer
    input  wire [7:0]  xfer_request,
    input  wire [31:0] xfer_wdata,
    output reg  [31:0] xfer_rdata,

    // Status output
    output reg  [2:0]  ack,
    output reg         parity_err,
    output reg         busy,
    output reg  [15:0] timestamp,

    // SWD Physical Interface
    output reg         swclk,
    output reg         swdio_o,
    input  wire        swdio_i,
    input  wire        swdio_i_fall,
    output reg         swdio_t       // 1=input, 0=output
);

    localparam [4:0] ST_IDLE      = 5'd0;
    localparam [4:0] ST_SWJ       = 4'd1;
    localparam [4:0] ST_XFER_REQ  = 4'd2;
    localparam [4:0] ST_TURN1     = 4'd3;
    localparam [4:0] ST_XFER_ACK  = 4'd4;
    localparam [4:0] ST_TURN_WR   = 4'd5;
    localparam [4:0] ST_XFER_RD   = 4'd6;
    localparam [4:0] ST_XFER_WR   = 4'd7;
    localparam [4:0] ST_XFER_WFRD = 4'd8;
    localparam [4:0] ST_XFER_WFWR = 4'd9;
    localparam [4:0] ST_TURN2     = 4'd10;
    localparam [4:0] ST_IDLE_CLK  = 4'd11;
    localparam [4:0] ST_DONE      = 4'd12;
    localparam [4:0] ST_TURN_WFWR = 4'd13;
    localparam [4:0] ST_RD_FINAL = 4'd14;
    localparam [4:0] ST_ACK_EXT  = 5'd15;
    localparam [4:0] ST_WTURN    = 5'd16;

    reg [7:0] active_request;
    reg  [4:0] state;
    reg  [8:0] lsm_cnt;
    reg  [15:0] delay_cnt;
    reg         is_read_op;
    reg  [2:0]  ack_samples;
    reg  [2:0]  ack_hold;
    reg  [1:0]  turn_wait;
    reg  [32:0] rd_samples;
    reg         rd_data_parity;
    reg  [32:0] wr_shift;
    reg  [255:0] swj_shift;
    reg  [3:0]  idle_cnt;
    reg  [15:0] timestamp_reg;

    reg         swdio_sample_async;
    reg         swdio_sample_sync1;
    reg         swdio_sampled_bit;
    wire        swdio_sample_fsm;
    wire        ila_sample_clk;

    wire [3:0]  active_delay;
    wire        step_tick;
    wire        req_parity;
    wire [7:0]  req_hdr;
    wire        wr_parity;
    wire [2:0]  ack_aligned;
    wire [2:0]  ack_aligned_next;
    wire [31:0] rd_data_aligned;
    wire        rd_parity_aligned;
    wire        dbg_start;
    wire        dbg_mode;
    wire [2:0]  dbg_ack;
    wire        dbg_parity_err;
    wire        dbg_busy;
    wire        dbg_swclk;
    wire        dbg_swdio_o;
    wire        dbg_swdio_i;
    wire        dbg_swdio_t;

    assign result_valid = (state == ST_DONE) && mode;
    assign next_ready = result_valid && delay_fast == 0 && ack == 1 && !parity_err;
    wire compact_ack = delay_fast == 0 && ack_delay == 0 && !data_phase;
    wire early_rx = rx_boundary && (ack_delay == 0);
    // The wrapper chooses early/late FCLK-domain input sampling.
    assign active_delay       = (state == ST_SWJ) ? clock_delay : delay_fast;
    assign step_tick          = (delay_cnt == {12'd0, active_delay});
    assign req_parity         = active_request[0] ^ active_request[1] ^ active_request[2] ^ active_request[3];
    assign req_hdr            = {1'b1, 1'b0, req_parity, active_request[3], active_request[2], active_request[1], active_request[0], 1'b1};
    assign wr_parity          = ^xfer_wdata;
    assign ack_aligned        = ack_samples;
    assign ack_aligned_next   = {swdio_sample_fsm, ack_samples[1:0]};
    assign rd_data_aligned    = rd_samples[31:0];
    assign rd_parity_aligned  = rd_samples[32];
    // The half-cycle input path feeds only capture registers. ACK decode and
    // parity checking use registered values with a full FCLK logic budget.
    assign swdio_sample_fsm = swdio_i_fall;
    assign ila_sample_clk   = clk;
    assign dbg_start         = start;
    assign dbg_mode          = mode;
    assign dbg_ack           = ack;
    assign dbg_parity_err    = parity_err;
    assign dbg_busy          = busy;
    assign dbg_swclk         = swclk;
    assign dbg_swdio_o       = swdio_o;
    assign dbg_swdio_i       = swdio_i;
    assign dbg_swdio_t       = swdio_t;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            swdio_sample_async <= 1'b0;
            swdio_sample_sync1 <= 1'b0;
            swdio_sampled_bit  <= 1'b0;
        end else begin
            swdio_sample_async <= swdio_i;
            swdio_sample_sync1 <= swdio_sample_async;
            swdio_sampled_bit  <= swdio_sample_sync1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            timestamp_reg <= 16'd0;
        end else begin
            timestamp_reg <= timestamp_reg + 1'b1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_request <= 0;
            state           <= ST_IDLE;
            lsm_cnt         <= 8'd0;
            delay_cnt       <= 16'd0;
            is_read_op      <= 1'b0;
            ack_samples     <= 3'd0;
            rd_samples      <= 33'd0;
            rd_data_parity  <= 1'b0;
            ack_hold        <= 3'd0;
            turn_wait       <= 2'd0;
            wr_shift        <= 33'd0;
            swj_shift       <= 256'd0;
            idle_cnt        <= 4'd0;

            swclk           <= 1'b1;
            swdio_o         <= 1'b1;
            swdio_t         <= 1'b0;
            xfer_rdata      <= 32'd0;
            ack             <= 3'd0;
            parity_err      <= 1'b0;
            busy            <= 1'b0;
            timestamp       <= 16'd0;
        end else begin
            case (state)
                ST_IDLE: begin
                    swclk      <= 1'b1;
                    // Preserve the last driven bit while SWCLK is high.
                    // A zero-idle write may have just raised its parity bit;
                    // forcing PARK here violates its hold time. The next
                    // accepted header drives START on a falling edge below.
                    // Keep direction until the next falling edge.
                    delay_cnt  <= 16'd0;
                    lsm_cnt    <= 8'd0;
                    idle_cnt   <= 4'd0;
                    busy       <= 1'b0;

                    if (start) begin
                        active_request <= xfer_request;
                        busy       <= 1'b1;
                        ack        <= 3'd0;
                        parity_err <= 1'b0;
                        is_read_op <= xfer_request[1];
                        ack_samples <= 3'd0;
                        rd_samples  <= 33'd0;
                        wr_shift <= {wr_parity,xfer_wdata};
                        swj_shift <= swj_data;

                        if (!mode) begin
                            state <= (swj_count == 8'd0) ? ST_DONE : ST_SWJ;
                        end else begin
                            state <= ST_XFER_REQ;
                            if (delay_fast == 0) begin
                                // Launch the first request half-cycle while
                                // accepting start, rather than an empty beat.
                                swclk <= 1'b0;
                                swdio_t <= 1'b0;
                                swdio_o <= req_hdr[0];
                                lsm_cnt <= 9'd1;
                            end
                        end
                    end
                end

                ST_SWJ: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;

                        if (!lsm_cnt[0]) begin
                            // Even beat: SWCLK low, drive next SWJ bit.
                            swclk   <= 1'b0;
                            swdio_t <= 1'b0;
                            swdio_o <= swj_shift[0];
                            swj_shift <= {1'b0,swj_shift[255:1]};
                        end else begin
                            // Odd beat: SWCLK high, one SWJ bit completed.
                            swclk <= 1'b1;
                        end

                        if (lsm_cnt[0] && ((lsm_cnt[8:1] + 8'd1) >= swj_count)) begin
                            state   <= ST_DONE;
                            lsm_cnt <= 9'd0;
                        end else begin
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end
                    end
                end

                ST_XFER_REQ: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        case (lsm_cnt)
                            8'd0:  begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[0]; lsm_cnt <= 8'd1;  end
                            8'd1:  begin swclk <= 1'b1; lsm_cnt <= 8'd2;  end
                            8'd2:  begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[1]; lsm_cnt <= 8'd3;  end
                            8'd3:  begin swclk <= 1'b1; lsm_cnt <= 8'd4;  end
                            8'd4:  begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[2]; lsm_cnt <= 8'd5;  end
                            8'd5:  begin swclk <= 1'b1; lsm_cnt <= 8'd6;  end
                            8'd6:  begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[3]; lsm_cnt <= 8'd7;  end
                            8'd7:  begin swclk <= 1'b1; lsm_cnt <= 8'd8;  end
                            8'd8:  begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[4]; lsm_cnt <= 8'd9;  end
                            8'd9:  begin swclk <= 1'b1; lsm_cnt <= 8'd10; end
                            8'd10: begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[5]; lsm_cnt <= 8'd11; end
                            8'd11: begin swclk <= 1'b1; lsm_cnt <= 8'd12; end
                            8'd12: begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= req_hdr[6]; lsm_cnt <= 8'd13; end
                            8'd13: begin swclk <= 1'b1; lsm_cnt <= 8'd14; end
                            8'd14: begin
                                // PARK low phase
                                swclk <= 1'b0;
                                swdio_o <= req_hdr[7];
                                lsm_cnt <= 8'd15;
                            end
                            8'd15: begin
                                // PARK high phase done, move to dedicated ACK turnaround.
                                swclk <= 1'b1;
                                turn_wait <= turn_extra;
                                state <= ST_TURN1;
                                lsm_cnt <= 8'd0;
                                ack_samples <= 3'd0;
                            end
                            default: begin
                                swclk <= 1'b1;
                                swdio_t <= 1'b0;
                                lsm_cnt <= 8'd0;
                            end
                        endcase
                    end
                end

                ST_TURN1: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b1;
                        if (turn_wait != 2'd0) begin
                            // Keep the line released and SWCLK low while a
                            // slow target finishes its turnaround response.
                            turn_wait <= turn_wait - 1'b1;
                            swclk <= 1'b0;
                        end else case (lsm_cnt)
                            8'd0: begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd1;
                            end
                            8'd1: begin
                                swclk   <= 1'b1;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd0;
                                state   <= (ack_delay == 0) ? ST_XFER_ACK : ST_ACK_EXT;
                                ack_samples <= 3'd0;
                                ack_hold <= 3'd0;
                            end
                            default: begin
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd0;
                            end
                        endcase
                    end
                end

                ST_XFER_ACK: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b1;
                        case (lsm_cnt)
                            8'd0: begin
                                // ACK[0] low phase.
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd1;
                            end
                            8'd1: begin
                                // Legacy receive pipeline (ack_delay=0).
                                swclk <= 1'b1;
                                if (early_rx) ack_samples[0] <= swdio_sample_fsm;
                                lsm_cnt <= 8'd2;
                            end
                            8'd2: begin
                                // ACK[0] falling edge occurs in SWCLK domain here.
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd3;
                            end
                            8'd3: begin
                                // ACK[1] high phase and consume ACK[0].
                                swclk <= 1'b1;
                                if (early_rx) ack_samples[1] <= swdio_sample_fsm;
                                else ack_samples[0] <= swdio_sample_fsm;
                                lsm_cnt <= 8'd4;
                            end
                            8'd4: begin
                                // ACK[1] falling edge occurs in SWCLK domain here.
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd5;
                            end
                            8'd5: begin
                                // ACK[2] high phase and consume ACK[1].
                                swclk <= 1'b1;
                                if (early_rx) begin
                                    ack_samples[2] <= swdio_sample_fsm;
                                    // This rise launches read D0 or begins
                                    // write/error turnaround. Decode next,
                                    // before emitting another SWCLK cycle.
                                    lsm_cnt <= 8'd8;
                                end else begin
                                    ack_samples[1] <= swdio_sample_fsm;
                                    lsm_cnt <= 8'd6;
                                end
                            end
                            8'd6: begin
                                // ACK[2] falling edge occurs in SWCLK domain here.
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd7;
                            end
                            8'd7: begin
                                // Capture only: keep the half-cycle input path
                                // out of ACK decode and clock-control logic.
                                // All valid no-data-phase ACKs need this rise:
                                // read D0, write turnaround, or error turnaround.
                                // Emit it while registering ACK2; decode remains
                                // on the following full-cycle register path.
                                swclk   <= compact_ack;
                                ack_samples[2] <= swdio_sample_fsm;
                                lsm_cnt <= 8'd8;
                            end
                            8'd8: begin
                                swclk <= 1'b0;
                                lsm_cnt <= 8'd0;
                                ack <= ack_samples;

                                if (ack_samples == 3'b001) begin
                                    if (is_read_op) begin
                                        rd_samples <= 33'd0;
                                        // In compact mode the preceding beat
                                        // already raised D0. Fall now, then
                                        // capture it on the next high phase.
                                        swclk <= early_rx ? 1'b0 : !compact_ack;
                                        lsm_cnt <= (early_rx || compact_ack) ? 8'd3 : ((ack_delay == 0) ? 8'd2 : 8'd0);
                                        state <= ST_XFER_RD;
                                    end else begin
                                        if (early_rx) begin
                                            // ACK2 capture launched turnaround;
                                            // complete its rise before D0.
                                            swclk <= 1'b0;
                                            lsm_cnt <= 8'd1;
                                            state <= ST_TURN_WR;
                                        end else if (ack_delay != 0) begin
                                            // The non-overlapping ACK sampler
                                            // has not clocked the ACK-to-write
                                            // turnaround yet. Keep both edges
                                            // before enabling host data output.
                                            swclk <= 1'b1;
                                            state <= ST_TURN_WR;
                                        end else if (compact_ack) begin
                                            // The preceding rise completed
                                            // turnaround. Launch D0 now.
                                            swclk <= 0; swdio_t <= 0;
                                            swdio_o <= wr_shift[0];
                                            wr_shift <= {1'b0,wr_shift[32:1]};
                                            lsm_cnt <= 1;
                                            state <= ST_XFER_WR;
                                        end else if (delay_fast == 0) begin
                                            // Beat 6 began write turnaround;
                                            // complete it here without another
                                            // TURN_WR pair of half-cycles.
                                            swclk <= 1'b1;
                                            state <= ST_XFER_WR;
                                        end else state <= ST_TURN_WR;
                                    end
                                end else if ((ack_samples == 3'b010) || (ack_samples == 3'b100)) begin
                                    if (data_phase) begin
                                        state <= is_read_op ? ST_XFER_WFRD : ST_TURN_WFWR;
                                    end else begin
                                        if (early_rx) begin
                                            swclk <= 0;
                                            state <= ST_WTURN;
                                        end else begin
                                            if (compact_ack) swclk <= 1;
                                            state <= ST_DONE;
                                        end
                                    end
                                end else begin
                                    // Protocol error ACK: exit immediately.
                                    if (early_rx) begin
                                        swclk <= 0;
                                        state <= ST_WTURN;
                                    end else begin
                                        if (compact_ack) swclk <= 1;
                                        state <= ST_DONE;
                                    end
                                end
                            end
                            default: begin
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd0;
                            end
                        endcase
                    end
                end

                ST_ACK_EXT: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 0;
                        swdio_t <= 1'b1;
                        // Turnaround's rising edge launched ACK0. Hold that
                        // high phase, fall, then capture before the NEXT rising
                        // edge launches ACK1. No sample is overwritten during
                        // a hold. Repeat the same schedule for all three bits.
                        case (lsm_cnt)
                            0,3,6: begin
                                swclk <= 1'b1;
                                if (ack_hold < ack_delay) ack_hold <= ack_hold + 1'b1;
                                else begin
                                    ack_hold <= 0;
                                    lsm_cnt <= lsm_cnt + 1'b1;
                                end
                            end
                            1,4,7: begin
                                swclk <= 1'b0;
                                lsm_cnt <= lsm_cnt + 1'b1;
                            end
                            2: begin
                                ack_samples[0] <= swdio_sample_fsm;
                                swclk <= 1'b1;
                                lsm_cnt <= 3;
                            end
                            5: begin
                                ack_samples[1] <= swdio_sample_fsm;
                                swclk <= 1'b1;
                                lsm_cnt <= 6;
                            end
                            8: begin
                                ack_samples[2] <= swdio_sample_fsm;
                                swclk <= 1'b0;
                                // Reuse registered ACK decode with a full
                                // logic cycle. Its next rise launches D0 or
                                // the write turnaround, not another ACK bit.
                                // WAIT/FAULT take a dedicated turnaround cycle:
                                // the target needs a full clock after ACK2
                                // before it can accept the next header.
                                if (!data_phase &&
                                    (({swdio_sample_fsm, ack_samples[1:0]} == 3'b010) ||
                                     ({swdio_sample_fsm, ack_samples[1:0]} == 3'b100))) begin
                                    // WAIT/FAULT: two-turnaround cycle before the
                                    // next header, then decode the stored bits.
                                    state   <= ST_WTURN;
                                    lsm_cnt <= 8'd0;
                                end else begin
                                    state   <= ST_XFER_ACK;
                                    lsm_cnt <= 8'd8;
                                end
                            end
                            default: begin state <= ST_DONE; end
                        endcase
                    end
                end

                ST_TURN_WR: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        case (lsm_cnt)
                            8'd0: begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd1;
                            end
                            8'd1: begin
                                swclk   <= 1'b1;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd0;
                                state   <= ST_XFER_WR;
                            end
                            default: begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd0;
                            end
                        endcase
                    end
                end

                ST_XFER_RD: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b1;
                        // 32 serial data samples shift into a register; parity is
                        // captured separately. No variable-index write decoder.
                        if (lsm_cnt == 8'd0) begin
                            swclk   <= 1'b0;
                            lsm_cnt <= 8'd1;
                        end else if (lsm_cnt < 8'd66) begin
                            if (lsm_cnt[0]) begin
                                // High phases: target drives next bit, while the
                                // current synchronized sample belongs to the
                                // previous SWCLK falling edge.
                                swclk <= 1'b1;
                                if (lsm_cnt != 8'd1) begin
                                    rd_samples[31:0] <= {swdio_sample_fsm,rd_samples[31:1]};
                                end
                            end else begin
                                // Low phases: SWCLK falling edge occurs here.
                                swclk <= 1'b0;
                            end
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end else if (lsm_cnt == 8'd66) begin
                            swclk   <= 1'b0;
                            // All 32 data bits are already registered. Reduce
                            // their parity a full FCLK before the final sample,
                            // leaving only one XOR on the half-cycle input path.
                            rd_data_parity <= ^rd_samples[31:0];
                            lsm_cnt <= 8'd67;
                        end else if (lsm_cnt == 8'd67) begin
                            // Consume the final parity bit and finish.
                            swclk      <= early_rx || (delay_fast == 0);
                            rd_samples[32] <= swdio_sample_fsm;
                            if (early_rx || delay_fast == 0) begin
                                // Complete the mandatory turnaround here. Keep
                                // SWDIO released until the next falling edge;
                                // the first idle clock can then drive low.
                                xfer_rdata <= rd_samples[31:0];
                                parity_err <= rd_data_parity ^ swdio_sample_fsm;
                                if (timestamp_en) timestamp <= timestamp_reg;
                                state <= early_rx ? ST_RD_FINAL : ((idle_cycles == 0) ? ST_DONE : ST_IDLE_CLK);
                                idle_cnt <= 0;
                                lsm_cnt <= 0;
                            end else lsm_cnt <= 8'd68;
                        end else if (lsm_cnt == 8'd68) begin
                            // Decision beat after all 33 bits captured.
                            swclk      <= 1'b0;
                            xfer_rdata <= rd_data_aligned;
                            parity_err <= (^rd_data_aligned) ^ rd_parity_aligned;
                            if (timestamp_en) begin
                                timestamp <= timestamp_reg;
                            end
                            lsm_cnt <= 8'd0;
                            state   <= ST_TURN2;
                        end else begin
                            swclk   <= 1'b0;
                            lsm_cnt <= 8'd0;
                        end
                    end
                end

                ST_XFER_WR: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b0;

                        // 33 write bits (32 data + parity).
                        if (lsm_cnt < 8'd66) begin
                            if (!lsm_cnt[0]) begin
                                swclk   <= 1'b0;
                                swdio_o <= wr_shift[0];
                                wr_shift <= {1'b0,wr_shift[32:1]};
                            end else begin
                                swclk <= 1'b1;
                                if (lsm_cnt == 65 && delay_fast == 0) begin
                                    if (timestamp_en) timestamp <= timestamp_reg;
                                    // The next falling edge is the first idle
                                    // bit, or the next accepted START. No empty
                                    // high beat is needed after parity.
                                    state <= (idle_cycles == 0) ? ST_DONE : ST_IDLE_CLK;
                                    idle_cnt <= 0;
                                    lsm_cnt <= 0;
                                end
                            end
                        end else begin
                            if (timestamp_en) begin
                                timestamp <= timestamp_reg;
                            end
                            lsm_cnt   <= 8'd0;
                            idle_cnt  <= 4'd0;
                            state     <= ST_IDLE_CLK;
                        end

                        if (lsm_cnt < 8'd66 && !(lsm_cnt == 65 && delay_fast == 0)) begin
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end
                    end
                end

                ST_XFER_WFRD: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b1;

                        // WAIT/FAULT read data phase: just clock through 33 bits.
                        if (lsm_cnt < 8'd66) begin
                            swclk   <= lsm_cnt[0];
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end else begin
                            lsm_cnt <= 8'd0;
                            state   <= ST_TURN2;
                        end
                    end
                end

                ST_XFER_WFWR: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;

                        // WAIT/FAULT write data phase: 33 dummy low bits.
                        if (lsm_cnt < 8'd66) begin
                            if (!lsm_cnt[0]) begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b0;
                                swdio_o <= 1'b0;
                            end else begin
                                swclk <= 1'b1;
                            end
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end else begin
                            lsm_cnt  <= 8'd0;
                            idle_cnt <= 4'd0;
                            state    <= ST_IDLE_CLK;
                        end
                    end
                end

                ST_TURN_WFWR: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        case (lsm_cnt)
                            8'd0: begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd1;
                            end
                            8'd1: begin
                                swclk   <= 1'b1;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd0;
                                state   <= ST_XFER_WFWR;
                            end
                            default: begin
                                swclk   <= 1'b0;
                                swdio_t <= 1'b1;
                                lsm_cnt <= 8'd0;
                            end
                        endcase
                    end
                end

                ST_TURN2: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;

                        // Read completion turnaround: target->host.
                        case (lsm_cnt)
                            8'd0: begin swclk <= 1'b0; swdio_t <= 1'b0; swdio_o <= 1'b0; end
                            8'd1: begin swclk <= 1'b1; end
                            default: begin
                                lsm_cnt  <= 8'd0;
                                idle_cnt <= 4'd0;
                                state    <= ST_IDLE_CLK;
                            end
                        endcase

                        if (lsm_cnt < 8'd2) begin
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end
                    end
                end

                ST_IDLE_CLK: begin
                    if (idle_cycles == 4'd0) begin
                        state <= ST_DONE;
                    end else if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b0;
                        swdio_o   <= 1'b0;

                        if (!lsm_cnt[0]) begin
                            swclk <= 1'b0;
                            lsm_cnt <= lsm_cnt + 1'b1;
                        end else begin
                            swclk <= 1'b1;
                            lsm_cnt <= lsm_cnt + 1'b1;
                            idle_cnt <= idle_cnt + 1'b1;
                            if ((idle_cnt + 1'b1) >= idle_cycles) begin
                                state   <= ST_DONE;
                                lsm_cnt <= 8'd0;
                            end
                        end
                    end
                end

                ST_RD_FINAL: begin
                    if (early_rx) begin
                        // The short-return path just consumed parity. Complete
                        // the target-to-host turnaround even with zero idle or
                        // a chained request. Keep SWDIO released throughout it.
                        if (!step_tick) delay_cnt <= delay_cnt + 1'b1;
                        else begin
                            delay_cnt <= 0;
                            swdio_t <= 1;
                            swclk <= lsm_cnt[0];
                            lsm_cnt <= 1;
                            if (lsm_cnt[0]) begin
                                lsm_cnt <= 0;
                                state <= (idle_cycles == 0) ? ST_DONE : ST_IDLE_CLK;
                            end
                        end
                    end else begin
                        xfer_rdata <= rd_data_aligned;
                        parity_err <= (^rd_data_aligned) ^ rd_samples[32];
                        if (timestamp_en) timestamp <= timestamp_reg;
                        state <= ST_DONE;
                    end
                end

                ST_WTURN: begin
                    if (!step_tick) begin
                        delay_cnt <= delay_cnt + 1'b1;
                    end else begin
                        delay_cnt <= 16'd0;
                        swdio_t   <= 1'b1;
                        case (lsm_cnt)
                            8'd0: begin
                                swclk   <= 1'b1;
                                lsm_cnt <= 8'd1;
                                if (early_rx) state <= ST_DONE;
                            end
                            8'd1: begin
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd8;
                                state   <= ST_XFER_ACK;
                            end
                            default: begin
                                swclk   <= 1'b0;
                                lsm_cnt <= 8'd8;
                                state   <= ST_XFER_ACK;
                            end
                        endcase
                    end
                end

                ST_DONE: begin
                    if (next_valid && next_ready) begin
                        // The previous result is consumed on this edge. Its
                        // registered ACK/parity gate acceptance of the next
                        // prefetched command; no speculative transfer on error.
                        active_request <= next_request;
                        is_read_op <= next_request[1];
                        ack <= 0; parity_err <= 0;
                        ack_samples <= 0; rd_samples <= 0;
                        wr_shift <= {^next_wdata,next_wdata};
                        busy <= 1; state <= ST_XFER_REQ;
                        delay_cnt <= 0; lsm_cnt <= 1; idle_cnt <= 0;
                        swclk <= 0; swdio_t <= 0; swdio_o <= 1;
                    end else begin
                        swclk <= 1;
                        // Keep a released input released throughout high idle.
                        busy <= 0; state <= ST_IDLE;
                    end
                end

                default: begin
                    state <= ST_IDLE;
                end
            endcase
        end
    end

`ifndef SYNTHESIS
always @(posedge clk) if ($test$plusargs("sttrace")) $display("ST t=%0t st=%0d lsm=%0d ack=%b", $time, state, lsm_cnt, ack_samples);
`endif

endmodule
