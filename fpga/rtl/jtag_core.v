`timescale 1ns/1ps
// ADIv5 JTAG-DP backend. Raw CMSIS operations remain available, while op=0
// presents the existing SWD posted-AP-read contract to packet/RTT/HSS engines.
// DP reads need a scan to collect their response; AP streams need only one
// 35-bit scan per word. IR is cached, including bypass bits around the DAP.
module jtag_core (
    input wire clk,rst_n,start,invalidate,
    input wire [2:0] operation, // 0 memory,1 raw DP/AP,2 IR,3 IDCODE,4 ABORT,5 JTAG seq,6 SWJ seq
    input wire [7:0] request,
    input wire [31:0] wdata,
    input wire [8:0] seq_count,
    input wire [255:0] seq_data,
    input wire seq_tms,
    input wire [7:0] ir_length,
    input wire [10:0] ir_before,ir_after,
    input wire [7:0] dr_before,dr_after,
    input wire [3:0] half_delay,idle_cycles,
    input wire late_return,
    input wire tdo,tdo_alternate,tdi_sense,
    input wire wait_abort,
    input wire next_valid,input wire [7:0] next_request,input wire [31:0] next_wdata,
    output wire next_ready,result_valid,busy,
    output reg [2:0] ack,output reg [31:0] rdata,
    output wire tck,tms,tdi,
    output wire [31:0] cached_instruction,
    output wire cache_valid,
    output wire [255:0] sequence_result,
    input wire fence_req,output reg fence_done,output reg fence_error,
    // Scan statistics: FCLK cycles spent waiting on the physical shifter, the
    // bits scanned and the number of completed scans. cycles/(2*bits) yields
    // half_delay+1, so software can confirm the clock the PHY really used.
    output reg [31:0] stat_cycles,output reg [31:0] stat_bits,
    output reg [31:0] stat_transfers,
    output wire debug_valid,
    output wire [31:0] debug_meta,debug_wdata,debug_tx,debug_sense,debug_rx,debug_alternate,debug_samples,
    output wire [5:0] debug_tx_req,
    output wire debug_wait_aborted,
    output wire [6:0] debug_bits
);
    localparam IDLE=0,ROUTE=1,RESET_TAP=2,IR_NAV=3,IR_PRE=4,IR_VALUE=5,IR_POST=6,IR_EXIT=7,
               DR_NAV=8,DR_PRE=9,DR_VALUE=10,DR_POST=11,DR_EXIT=12,EVALUATE=13,DONE=14,PHY_WAIT=15;
    reg [3:0] state,return_state;
    reg [2:0] op;
    reg [7:0] req;
    reg [31:0] value,desired_ir,ir_cache,saved_result;
    reg [31:0] fenced_result;
    reg fenced_result_valid;
    reg ir_valid,unknown_tap,maintenance,fence_consumed;
    reg [1:0] phase; // primary, collect DP read, launch CTRLSTAT, collect CTRLSTAT
    reg [6:0] retries;
    reg phy_start;
    reg [11:0] phy_count;
    reg phy_variable_tms,phy_tms,phy_exit,phy_capture;
    reg [1:0] phy_tdi_mode;
    reg [255:0] phy_tms_data,phy_tdi_data;
    wire phy_busy,phy_done;
    wire [255:0] phy_rx;
    wire [63:0] phy_tx_echo,phy_sense_echo,phy_rx_alternate;
    wire phy_wait_aborted;
    wire [11:0] phy_completed_bits;
    wire [63:0] debug_tx_frame=phy_tx_echo >> (5+dr_before);
    wire [63:0] debug_sense_frame=phy_sense_echo >> (5+dr_before);
    reg [34:0] scan_result;
    reg [63:0] dr_tms_bits,dr_tdi_bits;
    reg [6:0] dr_count;
    reg [3:0] capture_offset;
    reg phy_slow;
    reg phy_capture_rise;
    wire [3:0] phy_min_delay=phy_capture_rise ? 4'd3 : phy_slow ? 4'd1 : 4'd0;
    wire [3:0] phy_delay=half_delay<phy_min_delay ? phy_min_delay : half_delay;
    wire [2:0] scan_ack={scan_result[2],scan_result[0],scan_result[1]};
    wire [31:0] scan_data=scan_result[34:3];
    wire [31:0] normal_data=fenced_result_valid ? fenced_result : scan_data;
    wire [7:0] scan_req=phase==2 ? 8'h06 : phase!=0 ? 8'h0e : req;
    wire pending_fence=fence_req && !fence_consumed;
    assign busy=state!=IDLE || pending_fence;
    assign result_valid=state==DONE && !maintenance;
    assign next_ready=result_valid && op==0 && ack==1 && !pending_fence;
    assign debug_valid=state==EVALUATE;
    assign debug_meta={13'd0,op,phase,req,scan_result[2:0],scan_ack};
    assign debug_wdata=phase==0 ? value : 32'd0;
    assign debug_tx=debug_tx_frame[34:3];
    assign debug_sense=debug_sense_frame[34:3];
    assign debug_tx_req={debug_sense_frame[2:0],debug_tx_frame[2:0]};
    assign debug_rx=scan_data;
    wire [63:0] debug_alt_frame=phy_rx_alternate >> capture_offset;
    assign debug_alternate=debug_alt_frame[34:3];
    assign debug_samples={phy_rx_alternate[15:0],phy_rx[15:0]};
    assign debug_wait_aborted=phy_wait_aborted;
    assign debug_bits=phy_completed_bits[6:0];
    assign cached_instruction=ir_cache;
    assign cache_valid=ir_valid;
    assign sequence_result=phy_rx;
    jtag_shift u_shift(.clk(clk),.rst_n(rst_n),.start(phy_start),.count(phy_count),
        .half_delay(phy_delay),.variable_tms(phy_variable_tms),.tms_value(phy_tms),
        .exit_last(phy_exit),.capture(phy_capture),.tdi_mode(phy_tdi_mode),
        .capture_rise(phy_capture_rise),
        .tms_data(phy_tms_data),.tdi_data(phy_tdi_data),.tdo(tdo),.tdo_alternate(tdo_alternate),.tdi_sense(tdi_sense),
        .abort_on_wait(wait_abort && state==PHY_WAIT && return_state==EVALUATE && (op==0 || op==1) && desired_ir!=8),
        .ack_offset(capture_offset),.abort_idle_cycles(idle_cycles),
        .tck(tck),.tms(tms),.tdi(tdi),.busy(phy_busy),.done(phy_done),.rx_data(phy_rx),
        .tx_echo(phy_tx_echo),.sense_echo(phy_sense_echo),.rx_alternate(phy_rx_alternate),
        .wait_aborted(phy_wait_aborted),.completed_bits(phy_completed_bits));
    task shift_segment;
        input [11:0] n;
        input variable_mode,tm,exit_bit,cap;
        input [1:0] data_mode;
        input [255:0] tms_bits,data_bits;
        input [3:0] following;
        begin
            phy_count<=n;phy_variable_tms<=variable_mode;phy_tms<=tm;phy_exit<=exit_bit;
            phy_capture<=cap;phy_tdi_mode<=data_mode;phy_tms_data<=tms_bits;
            phy_tdi_data<=data_bits;phy_start<=1;return_state<=following;state<=PHY_WAIT;
            // TAP/IR/raw sequences tolerate a lower clock than the requested
            // maximum. DR streams retain the full clock and pipeline TDO.
            phy_slow<=state!=DR_PRE;
            phy_capture_rise<=following==DONE && (operation==5 || operation==6);
        end
    endtask
    task memory_request;
        input [7:0] nr;input [31:0] nv;
        begin
            op<=0;req<=nr;value<=nv;phase<=0;maintenance<=0;retries<=64;
            desired_ir<=!nr[0] && !nr[1] && nr[3:2]==0 ? 8 : nr[0] ? 11 : 10;
            state<=ROUTE;
        end
    endtask
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;return_state<=IDLE;op<=0;req<=0;value<=0;desired_ir<=10;ir_cache<=0;
            ir_valid<=0;unknown_tap<=1;maintenance<=0;fence_consumed<=0;phase<=0;retries<=64;
            ack<=0;rdata<=0;saved_result<=0;scan_result<=0;phy_start<=0;phy_count<=0;
            fenced_result<=0;fenced_result_valid<=0;
            phy_variable_tms<=0;phy_tms<=0;phy_exit<=0;phy_capture<=0;phy_tdi_mode<=0;
            phy_tms_data<=0;phy_tdi_data<=0;fence_done<=0;fence_error<=0;
            stat_cycles<=0;stat_bits<=0;stat_transfers<=0;
            dr_tms_bits<=0;dr_tdi_bits<=0;dr_count<=0;capture_offset<=0;
            phy_slow<=0;phy_capture_rise<=0;
        end else begin
            phy_start<=0;fence_done<=0;
            if(!fence_req) fence_consumed<=0;
            if(invalidate) begin ir_valid<=0;unknown_tap<=1;fenced_result_valid<=0;end
            case(state)
            IDLE: begin
                if(start) begin
                    if(operation!=0 || (!request[0] && !request[1] && request[3:2]==0)) fenced_result_valid<=0;
                    op<=operation;req<=request;value<=wdata;phase<=0;retries<=64;maintenance<=0;
                    desired_ir<=operation==2 ? wdata : operation==3 ? 14 :
                                operation==4 || (operation==0 && !request[0] && !request[1] && request[3:2]==0) ? 8 :
                                request[0] ? 11 : 10;
                    if(operation==5 || operation==6) begin
                        ir_valid<=0;unknown_tap<=1;ack<=1;
                        shift_segment({3'd0,seq_count},operation==6,seq_tms,0,1,operation==6 ? 1 : 2,
                                      seq_data,seq_data,DONE);
                    end else state<=ROUTE;
                end else if(pending_fence) begin
                    maintenance<=1;op<=0;phase<=2;desired_ir<=10;retries<=64;state<=ROUTE;
                    fence_consumed<=1;fence_error<=0;
                end
            end
            ROUTE: if(ir_length==0 || ir_length>32 || dr_before+dr_after>7) begin ack<=7;state<=DONE;end
            else if(unknown_tap) state<=RESET_TAP;
            else if(!ir_valid || ir_cache!=desired_ir || op==2) state<=IR_NAV;
            else state<=DR_NAV;
            RESET_TAP: begin
                unknown_tap<=0;ir_valid<=0;
                shift_segment(6,1,0,0,0,1,256'h1f,0,ROUTE);
            end
            IR_NAV: shift_segment(4,1,0,0,0,1,3,0,IR_PRE);
            IR_PRE: if(ir_before!=0) shift_segment({1'b0,ir_before},0,0,0,0,1,0,0,IR_VALUE);
                    else state<=IR_VALUE;
            IR_VALUE: shift_segment({4'd0,ir_length},0,0,ir_after==0,0,2,0,{224'd0,desired_ir},IR_POST);
            IR_POST: if(ir_after!=0) shift_segment({1'b0,ir_after},0,0,1,0,1,0,0,IR_EXIT);
                     else state<=IR_EXIT;
            IR_EXIT: begin
                ir_cache<=desired_ir;ir_valid<=1;
                shift_segment(2,1,0,0,0,1,1,0,op==2 ? DONE : DR_NAV);
                if(op==2) ack<=1;
            end
            // A complete DR path is a SINGLE uninterrupted shift segment:
            // navigation, bypass, 35 data bits, Exit1, Update and Idle.
            // This removes FSM bubbles between each part of every word.
            DR_NAV: begin
                // Long physical TDO return: sample one scan bit later. Two
                // dummy bits precede the request, so UPDATE still sees exactly
                // the same register value. The first extra output bit captures
                // the last response bit while TDO remains in SHIFT_DR; the
                // second exits SHIFT, avoiding a fast TDO output-disable race.
                dr_tms_bits<=(64'd3 << (4+dr_before+(op==3 ? 32 : 35)+dr_after)) | 1;
                dr_tdi_bits<=(op==3 ? 64'd0 : {29'd0,(phase==0 ? value : 32'd0),scan_req[3:1]}) << (5+dr_before);
                dr_count<=7+dr_before+(op==3 ? 32 : 35)+dr_after+idle_cycles;
                capture_offset<=3+dr_before+(late_return ? 1 : 0);state<=DR_PRE;
            end
            DR_PRE: shift_segment({5'd0,dr_count},1,0,0,1,2,{192'd0,dr_tms_bits},{192'd0,dr_tdi_bits},EVALUATE);
            PHY_WAIT: begin
                stat_cycles<=stat_cycles+1'b1;
                if(phy_done) begin
                    stat_bits<=stat_bits+{20'd0,phy_completed_bits};
                    stat_transfers<=stat_transfers+1'b1;
                    if(return_state==EVALUATE) scan_result<=phy_rx >> capture_offset;
                    if(return_state==DONE && (op==5 || op==6)) rdata<=phy_rx[31:0];
                    state<=return_state;
                end
            end
            EVALUATE: begin
                if(op==3) begin ack<=1;rdata<=scan_result[31:0];state<=DONE;end
                else if(op==4 || (op==0 && phase==0 && desired_ir==8)) begin ack<=1;state<=DONE;end
                else if(scan_ack==2 && phase!=0 && retries!=0) begin
                    retries<=retries-1'b1;state<=DR_NAV;
                end else if(scan_ack!=1) begin ack<=scan_ack;state<=DONE;end
                else if(op==0 && phase==0 && !req[0] && req[1]) begin
                    saved_result<=normal_data;fenced_result_valid<=0;
                    // RDBUFF already captures the last AP result. Check sticky
                    // errors before publishing it; other DP reads need one
                    // extra scan to collect the CURRENT DP register value.
                    phase<=req[3:2]==3 ? 2 : 1;desired_ir<=10;state<=ROUTE;
                end else if(op==0 && phase==2) begin
                    // CTRL/STAT consumes the outstanding AP reply. JTAG
                    // RDBUFF is RAZ and cannot reload it like SWD RDBUFF.
                    // Keep the consumed reply for the next frontend access.
                    if(maintenance && !fenced_result_valid) begin fenced_result<=scan_data;fenced_result_valid<=1;end
                    phase<=3;state<=DR_NAV;
                end
                else if(op==0 && phase==3) begin
                    ack<=(scan_data & 32'ha2)!=0 ? 4 : 1;
                    fence_error<=(scan_data & 32'ha2)!=0;
                    rdata<=saved_result;state<=DONE;
                end else begin
                    ack<=1;rdata<=op==0 && phase==0 ? normal_data : scan_data;
                    if(op==0 && phase==0) fenced_result_valid<=0;
                    state<=DONE;
                end
            end
            DONE: begin
                if(maintenance) begin fence_done<=1;fence_error<=ack!=1;state<=IDLE;end
                else if(next_valid && next_ready) memory_request(next_request,next_wdata);
                else state<=IDLE;
            end
            default: state<=IDLE;
            endcase
        end
    end
endmodule
