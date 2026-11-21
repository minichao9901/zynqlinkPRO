`timescale 1ns/1ps
// The AP request/response interface used by packet, RTT and sampling engines.
// SWJ output sequences use the same one-SWCLK-per-quartet waveform as transfers.
module selectio_live_swd (
    input wire host_clk, quad_clk, reset, granted,
    input wire start, mode, input wire [7:0] request, input wire [31:0] wdata,
    input wire [255:0] seq_data, input wire [7:0] seq_count,
    input wire [5:0] sample_slot, input wire [3:0] idle, input wire half_rate,
    output wire busy, valid, output wire [2:0] ack, output wire parity,
    output wire [31:0] rdata,
    input wire [3:0] rx, output wire [3:0] clocks, data, release_bits
);
    // The large SWJ data register already exists on the AXI side. The host
    // holds it throughout this request, including its synchronized start.
    (* ASYNC_REG="TRUE" *) reg [2:0] reset_sync=7;
    always @(posedge quad_clk or posedge reset)
        if(reset) reset_sync<=7;else reset_sync<={reset_sync[1:0],1'b0};
    wire launch, active_mode;
    wire [3:0] op;
    wire [31:0] value;
    wire [7:0] length;
    wire [5:0] slot;
    wire [3:0] idle_count;
    wire link_done, link_parity;
    wire [2:0] link_ack;
    wire [31:0] link_value;
    reg [255:0] shifting;
    reg [7:0] left;
    wire slow;
    reg upper_half;
    wire bit_end=!slow || upper_half;
    wire seq_done=!active_mode && ((launch && length==0) || (left==1 && bit_end));
    selectio_command_bridge #(.REQUEST_BITS(56),.RESPONSE_BITS(36)) crossing(
        .host_clk(host_clk),.io_clk(quad_clk),.reset(reset),.host_start(start),
        .host_request({mode,request[3:0],wdata,seq_count,sample_slot,idle,half_rate}),
        .host_busy(busy),.host_done(valid),.host_response({ack,parity,rdata}),
        .granted(granted),.io_start(launch),.io_request({active_mode,op,value,length,slot,idle_count,slow}),
        .io_done(link_done || seq_done),
        .io_response(active_mode ? {link_ack,link_parity,link_value} : {3'd1,33'd0}));
    wire [3:0] link_clk,link_data,link_release;
    swd200_link transaction(
        .clk(quad_clk),.reset(reset_sync[2]),.rate({1'b0,!slow}),.ack_sample(slot),.data_sample(slot),
        .idle_cycles(idle_count),.release_guard(3'b0),.start(launch && active_mode),
        .enter_swd(1'b0),.header({2'b10,^op,op,1'b1}),.write_packet({^value,value}),
        .done(link_done),.ack(link_ack),.parity_error(link_parity),.read_data(link_value),
        .rx_slots(rx),.clk_slots(link_clk),.data_slots(link_data),.release_slots(link_release));
    always @(posedge quad_clk) begin
        if(reset_sync[2]) begin left<=0;upper_half<=0;end
        else if(launch && !active_mode) begin left<=length;shifting<=seq_data;upper_half<=0;end
        else if(left!=0) begin
            upper_half<=!upper_half;
            if(bit_end) begin left<=left-1'b1;shifting<={1'b0,shifting[255:1]};end
        end
    end
    assign clocks=left!=0 ? (slow ? {4{upper_half}} : 4'b1100) : link_clk;
    assign data=left!=0 ? {4{shifting[0]}} : link_data;
    assign release_bits=left!=0 ? 0 : link_release;
endmodule

module selectio_live_jtag (
    input wire host_clk, octet_clk, reset, granted, start,
    input wire [11:0] count, input wire variable_tms,tms,exit_last,capture,
    input wire [1:0] tdi_mode, input wire [255:0] tms_data,tdi_data,
    input wire [6:0] sample_slot, input wire half_rate,
    output wire done, output wire [63:0] received,
    input wire [7:0] rx, output wire [23:0] lanes
);
    (* ASYNC_REG="TRUE" *) reg [2:0] reset_sync=7;
    always @(posedge octet_clk or posedge reset)
        if(reset) reset_sync<=7;else reset_sync<={reset_sync[1:0],1'b0};
    wire launch,complete;
    wire [11:0] length;
    wire variable,level,finish,sense;
    wire [1:0] drive;
    wire [6:0] slot;
    wire [63:0] bits_out;
    wire slow;
    // jtag_core keeps the two 256-bit segment payloads settled until DONE.
    selectio_command_bridge #(.REQUEST_BITS(26),.RESPONSE_BITS(64)) crossing(
        .host_clk(host_clk),.io_clk(octet_clk),.reset(reset),.host_start(start),
        .host_request({count,variable_tms,tms,exit_last,capture,tdi_mode,sample_slot,half_rate}),
        .host_busy(),.host_done(done),.host_response(received),
        .granted(granted),.io_start(launch),.io_request({length,variable,level,finish,sense,drive,slot,slow}),
        .io_done(complete),.io_response(bits_out));
    jtag200_segment segment(.clk(octet_clk),.reset(reset_sync[2]),.start(launch),.count(length),
        .variable_tms(variable),.tms_value(level),.exit_last(finish),.capture(sense),
        .tdi_mode(drive),.tms_data(tms_data),.tdi_data(tdi_data),.half_slots(slow ? 3'd4 : 3'd2),
        .sample_offset(slot),.advance_tms(1'b1),.advance_tdi(1'b1),.rx_word(rx),
        .lane_word(lanes),.done(complete),.rx_data(bits_out));
endmodule
