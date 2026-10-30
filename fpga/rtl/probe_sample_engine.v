`timescale 1ns/1ps
// Autonomous AHB-AP sampler. Configuration and FIFO share the 0x60..0x7c
// AXI window in swd_controller. A complete sample is published atomically.
// Plan entries are aligned word addresses; PS gathers subword variables.
module probe_sample_engine #(
    parameter integer FIFO_SAMPLES=16,
    parameter integer RETRIES=64,
    parameter integer TIMEOUT=262143
)(
    input wire clk, rst_n,
    input wire wr, rd,
    input wire [2:0] waddr, raddr,
    input wire [31:0] wdata,
    output reg [31:0] rdata,
    input wire available,
    input wire stream_pop,
    output wire stream_empty,
    output wire [31:0] stream_data,
    output wire [31:0] timer_tick,
    output wire [31:0] validation_count,
    output wire active,
    output reg core_start,
    output reg [7:0] core_req,
    output reg [31:0] core_wdata,
    output wire core_next_valid,
    output wire [7:0] core_next_req,
    output wire [31:0] core_next_wdata,
    input wire core_busy, core_result_valid, core_next_ready,
    input wire [2:0] core_ack,
    input wire core_parity_err,
    input wire [31:0] core_rdata
);
    localparam IDLE=0, ISSUE=1, WAIT=2, ADVANCE=3, COMMIT=4, PUBLISH=5;
    localparam FAST_DRW=5, FAST_LAST=6;
    reg [2:0] state;
    reg enabled, fault;
    reg [4:0] count, plan_index, item;
    // Contiguous plans use the SWD posted-read pipeline. Sparse plans keep
    // the TAR-per-word path because their addresses cannot be auto-incremented.
    reg fast_span;
    reg [23:0] span_last;
    reg [31:0] plan[0:23];
    // Slot stride is 32 words: timestamp followed by up to 24 data words.
    localparam FIFO_ADDR_W=$clog2(FIFO_SAMPLES)+5;
    (* ram_style="block" *) reg [31:0] fifo[0:FIFO_SAMPLES*32-1];
    reg fifo_wen;
    reg [FIFO_ADDR_W-1:0] fifo_waddr;
    reg [31:0] fifo_wdata;
    // Keep the RAM write process free of async reset and use one physical
    // write port. Reset only the ownership pointers, not sample storage.
    always @(posedge clk) if(fifo_wen) fifo[fifo_waddr]<=fifo_wdata;
    reg [31:0] head, tail;
    reg [4:0] read_word;
    reg [31:0] tick, deadline, sample_time, period, skipped, errors;
    // Fractional 24 MHz timer remains correct when PS changes FCLK.
    reg [31:0] clock_hz, fraction;
    wire [32:0] phase_sum = {1'b0,fraction}+33'd24000000;
    wire tick_en = phase_sum >= {1'b0,clock_hz};
    reg [2:0] phase;
    reg [7:0] retries;
    reg [$clog2(TIMEOUT+1)-1:0] watchdog;
    reg setup_needed;
    // Single aligned word: after the first prime, every later sample is one
    // DRW read.  CSW keeps TAR fixed, so the posted result is returned by the
    // next sample's DRW exactly like superlinkPRO's swd_read_word_pipe().
    reg fixed_pipe;
    reg pending;
    reg [31:0] pending_time, launch_time;
    // A JTAG CTRL/STAT fence also validates the outstanding single-word AP
    // result. It may enter the FIFO after the fence, on the next DRW scan.
    assign validation_count=head+((fixed_pipe && pending) ? 32'd1 : 32'd0);
    wire [31:0] used = head-tail;
    wire span_end = span_last[item];
    wire next_span_end = span_last[item+1];
    wire take_word = (rd && raddr==5) || stream_pop;
    wire pop = take_word && used!=0 && read_word==count;
    assign stream_empty = used==0;
    // Read the cursor that will be visible AFTER this edge. This sustains
    // one word/clock for both AXI and the PL packetizer with synchronous RAM.
    // A timestamp is written on PUBLISH's edge; forward that collision so
    // the newly published sample never exposes the old slot's timestamp.
    wire clear_fifo = wr && waddr==0 && wdata[1] && !active;
    wire [FIFO_ADDR_W-1:0] fifo_raddr = clear_fifo ? 0 :
        (take_word && used!=0) ? (pop ? ((tail+1)%FIFO_SAMPLES)*32 :
                                     (tail%FIFO_SAMPLES)*32+read_word+1) :
                                (tail%FIFO_SAMPLES)*32+read_word;
    reg [31:0] fifo_rdata, fifo_forward_data;
    reg fifo_forward;
    always @(posedge clk) begin
        fifo_rdata <= fifo[fifo_raddr];
        fifo_forward <= fifo_wen && fifo_waddr==fifo_raddr;
        fifo_forward_data <= fifo_wdata;
    end
    wire [31:0] fifo_current = fifo_forward ? fifo_forward_data : fifo_rdata;
    assign stream_data = used!=0 ? fifo_current : 0;
    assign timer_tick = tick;
    wire ctrl = wr && waddr==0;
    wire finishing = state!=IDLE || (!enabled && pending) || (fault && core_busy);
    assign active = enabled || finishing;
    // Consume the current result and launch the next posted transfer on the
    // same ST_DONE edge of swd_core.  This removes the idle gap between DRW
    // transactions while retaining the old retry path for WAIT/FAULT.
    assign core_next_valid = (state==WAIT) && core_result_valid &&
                             core_ack==3'd1 && !core_parity_err &&
                             count>1 && ((phase==3) || (phase==FAST_DRW));
    assign core_next_req = (phase==3 ? span_end : next_span_end) ? 8'h0e : 8'h0f;
    assign core_next_wdata = 0;
    always @* begin
        case(raddr)
        0: rdata={16'h4853,3'd0,count,7'd0,enabled};
        1: rdata={used[15:0],8'd0,3'd0,fault,2'd0,finishing,enabled};
        2: rdata={27'd0,plan_index};
        3: rdata=plan[plan_index<24 ? plan_index : 0];
        4: rdata=period;
        5: rdata=used!=0 ? fifo_current : 0;
        // Data-only window: skip the timestamp word and advance the same
        // FIFO cursor.  Version-2 HSS uses nominal period timestamps, so a
        // sample needs one AXI read per value instead of timestamp+value.
        6: rdata=tick;
        7: rdata=skipped;
        default: rdata=0;
        endcase
    end
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE; enabled<=0; fault<=0; count<=0; plan_index<=0; fast_span<=0;span_last<=24'hffffff;
            item<=0; head<=0; tail<=0; read_word<=0; tick<=0; deadline<=0;
            sample_time<=0; period<=2400; skipped<=0; errors<=0;
            clock_hz<=100000000; fraction<=0; phase<=0; retries<=0;
            watchdog<=0; setup_needed<=1; fixed_pipe<=0; pending<=0;
            pending_time<=0; launch_time<=0; core_start<=0; core_req<=0;
            core_wdata<=0; fifo_wen<=0; fifo_waddr<=0; fifo_wdata<=0;
        end else begin
            core_start<=0; fifo_wen<=0;
            if(tick_en) begin tick<=tick+1'b1; fraction<=phase_sum-clock_hz; end
            else fraction<=phase_sum[31:0];
            if(take_word && used!=0) begin
                if(pop) begin tail<=tail+1'b1; read_word<=0; end
                else read_word<=read_word+1'b1;
            end
            // Configuration is immutable while enabled or finishing a sample.
            if(wr && !active) begin
                case(waddr)
                2: plan_index<=wdata[4:0];
                3: if(plan_index<24) plan[plan_index]<={wdata[31:2],2'b00};
                4: period<=wdata<24 ? 24 : (wdata>24000000 ? 24000000 : wdata);
                6: begin clock_hz<=wdata<24000000 ? 24000000 : wdata; fraction<=0; end
                7: begin tick<=wdata; deadline<=wdata; fraction<=0; end
                default: ;
                endcase
            end
            if(ctrl) begin
                // bit1 clears FIFO/counters only after a graceful stop.
                if(wdata[1] && !active) begin
                    head<=0; tail<=0; read_word<=0; skipped<=0; errors<=0; fault<=0;
                end
                if(!wdata[0]) enabled<=0;
                else if(!active && wdata[12:8]!=0 && wdata[12:8]<=24 && available) begin
                    enabled<=1; count<=wdata[12:8]; setup_needed<=1; fixed_pipe<=0; pending<=0;
                    fast_span<=1;
                    if ({1'b0,plan[0][9:0]} + (wdata[12:8]*4) > 1024) fast_span<=0;
                    for (integer ci=1; ci<24; ci=ci+1)
                        if (ci < wdata[12:8] && plan[ci] != plan[0] + (ci*4))
                            fast_span<=0;
                    for(integer si=0;si<24;si=si+1)
                        if(si==23) span_last[si]<=1;
                        else span_last[si]<=si+1>=wdata[12:8] || plan[si+1]!=plan[si]+4 || plan[si][9:0]==10'h3fc;
                    deadline<=tick; fault<=0;
                end
            end
            // One deadline per cycle avoids combinational division. Overruns
            // advance the nominal timeline instead of making catch-up samples.
            if(enabled && $signed(tick-deadline)>=0 && !(ctrl && !wdata[0])) begin
                deadline<=deadline+period;
                // Reserve one FIFO slot for the final posted result. A DAP
                // preemption can then flush and release SWD even if USB stalls.
                if(state==IDLE && used<((fast_span && count==1) ? FIFO_SAMPLES-1 : FIFO_SAMPLES) && available) begin
                    sample_time<=pending ? pending_time : deadline;
                    launch_time<=deadline; item<=0;
                    phase<=setup_needed ? 0 :
                           ((fast_span && count==1 && fixed_pipe) ? FAST_DRW : 2);
                    retries<=RETRIES; state<=ISSUE;
                end else skipped<=skipped+1'b1;
            end
            case(state)
            IDLE: if (!enabled && pending && used<FIFO_SAMPLES && available) begin
                sample_time<=pending_time; item<=0; phase<=FAST_LAST;
                retries<=RETRIES; state<=ISSUE;
            end
            ISSUE: if(!core_busy) begin
                case(phase)
                0: begin core_req<=8'h08; core_wdata<=0; end // SELECT AP0, bank0
                1: begin core_req<=8'h01; core_wdata<=count>1 ? 32'h23000012 : 32'h23000002; end
                2: begin core_req<=8'h05; core_wdata<=plan[item]; end // TAR
                3: begin core_req<=8'h0f; core_wdata<=0; end // prime posted DRW
                4: begin core_req<=8'h0e; core_wdata<=0; end // RDBUFF
                FAST_DRW: begin core_req<=8'h0f; core_wdata<=0; end
                FAST_LAST: begin core_req<=8'h0e; core_wdata<=0; end
                default: ;
                endcase
                core_start<=1; watchdog<=TIMEOUT; state<=WAIT;
            end
            WAIT: begin
                if(core_result_valid) begin
                    if(core_ack==2 && !core_parity_err && retries!=0) begin
                        retries<=retries-1'b1; state<=ISSUE;
                    end else if(core_ack!=1 || core_parity_err) begin
                        errors<=errors+1'b1; fault<=1; enabled<=0; pending<=0; state<=IDLE;
                    end else begin
                        if(phase==4 || phase==FAST_DRW || phase==FAST_LAST) begin
                            fifo_wen<=1; fifo_waddr<=(head%FIFO_SAMPLES)*32+item+1;
                            fifo_wdata<=core_rdata;
                        end
                        if (phase==3) begin
                            if (count==1) begin
                                pending<=1; pending_time<=launch_time;
                                fixed_pipe<=1; setup_needed<=0; state<=IDLE;
                            end else begin
                                phase<=span_end ? FAST_LAST : FAST_DRW;
                                state<=core_next_ready ? WAIT : ISSUE;
                            end
                        end else if (phase==FAST_DRW) begin
                            if (count==1) begin pending_time<=launch_time; state<=COMMIT; end
                            else begin
                                item<=item+1'b1;
                                if (next_span_end) phase<=FAST_LAST;
                                state<=core_next_ready ? WAIT : ISSUE;
                            end
                        end else if (phase==FAST_LAST) begin
                            pending<=0;
                            if(item+1==count) state<=COMMIT;
                            else begin item<=item+1'b1;phase<=2;state<=ISSUE;end
                        end else state<=ADVANCE;
                        watchdog<=TIMEOUT; retries<=RETRIES;
                    end
                end else if(watchdog==0) begin
                    errors<=errors+1'b1; fault<=1; enabled<=0; pending<=0; state<=IDLE;
                end else watchdog<=watchdog-1'b1;
            end
            ADVANCE: if(!core_busy) begin
                retries<=RETRIES;
                if(phase==4) begin
                    if(item+1==count) state<=COMMIT;
                    else begin item<=item+1'b1; phase<=2; state<=ISSUE; end
                end else begin phase<=phase+1'b1; state<=ISSUE; end
            end
            COMMIT: begin
                fifo_wen<=1;fifo_waddr<=(head%FIFO_SAMPLES)*32;fifo_wdata<=sample_time;
                state<=PUBLISH;
            end
            PUBLISH: begin
                // The registered timestamp write lands on this edge. Publish
                // afterwards so an immediate AXI FIFO read cannot see old RAM.
                head<=head+1'b1; setup_needed<=0;
                if (fast_span && count==1) fixed_pipe<=1;
                state<=IDLE;
            end
            default: state<=IDLE;
            endcase
        end
    end
endmodule
