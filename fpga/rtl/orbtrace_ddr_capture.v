`timescale 1ns/1ps
// RAW4 reference-domain capture owner -> SYS framed byte stream. The source
// sampler, parser drain and EOF are separate phases. Configuration stays held
// until the controller retires the writer; snapshot fields are frozen before
// the completion handshake. No USB reset signal belongs in this module.
module orbtrace_ddr_capture #(
  parameter FIFO_ADDR_BITS=9
)(
  input wire clk,input wire ref_clk,input wire rst_n,input wire hold,
  input wire start,input wire [31:0] requested_ticks,
  input wire stop_request,input wire [1:0] stop_reason,
  input wire [127:0] source_frame,source_tail,input wire [4:0] source_tail_bytes,
  input wire source_frame_event,source_parser_error,source_sync_event,
  input wire source_tail_ambiguous,input wire receiver_ready,
  output wire sampler_gate,parser_enable,parser_clear,
  output wire [127:0] frame_data,output wire [4:0] frame_bytes,
  output wire frame_last,frame_valid,input wire frame_ready,
  output wire source_active,output reg snapshot_valid,
  output reg [31:0] elapsed_ticks,observed_frames,dropped_frames,parser_errors,
  output reg [31:0] sync_count,frame_highwater,ready_losses,
  output reg [4:0] tail_bytes,output reg tail_ambiguous,output reg [1:0] reason
);
  wire reset=!rst_n || !hold;
  reg command_epoch;
  reg [31:0] ticks_held;
  always @(posedge clk or posedge reset)
    if(reset)begin command_epoch<=0;ticks_held<=0;end
    else if(start)begin command_epoch<=!command_epoch;ticks_held<=requested_ticks;end
  (* ASYNC_REG="TRUE" *) reg [1:0] ref_reset;
  always @(posedge ref_clk or posedge reset)
    if(reset)ref_reset<=3;else ref_reset<={ref_reset[0],1'b0};
  (* ASYNC_REG="TRUE" *) reg [2:0] command_sync;
  (* ASYNC_REG="TRUE" *) reg [1:0] stop_sync,ready_sync;
  reg seen_command;
  reg [3:0] state;
  reg [2:0] drain;
  reg [31:0] ticks_ref;
  reg [1:0] stop_reason_ref;
  wire window_open,window_done,window_rejected;
  wire [31:0] elapsed_ref;
  wire [1:0] reason_ref;
  localparam WAIT_COMMAND=0,SETTLE=1,CLEAR_PARSER=2,START_WINDOW=3,
             WAIT_OPEN=4,RUN=5,DRAIN=6,EOF_WAIT=7,FINISHED=8;
  assign sampler_gate=window_open;
  assign parser_clear=state==CLEAR_PARSER;
  assign parser_enable=state==WAIT_OPEN || state==RUN || state==DRAIN;
  orbtrace_ref_window window(.ref_clk(ref_clk),.rst(ref_reset[1]),.start(state==START_WINDOW),
    .stop(stop_sync[1]),.stop_reason(stop_reason_ref),.requested_ticks(ticks_ref),
    .window_open(window_open),.done(window_done),.rejected(window_rejected),.elapsed_ticks(elapsed_ref),.reason(reason_ref));
  reg [31:0] observed_ref,dropped_ref,parser_ref,sync_ref,highwater_ref,ready_losses_ref;
  reg previous_ready,finished_ref;
  wire [FIFO_ADDR_BITS:0] fifo_level;
  wire fifo_wr_ready;
  wire capture_frame=parser_enable && source_frame_event;
  wire fifo_wr_valid=capture_frame || state==EOF_WAIT;
  wire [133:0] fifo_wr_data=state==EOF_WAIT ? {1'b1,source_tail_bytes,source_tail} : {1'b0,5'd16,source_frame};
  wire [133:0] fifo_rd_data;
  orbtrace_frame_async_fifo #(.ADDR_BITS(FIFO_ADDR_BITS)) fifo(.wr_clk(ref_clk),.wr_rst(ref_reset[1]),
    .wr_data(fifo_wr_data),.wr_valid(fifo_wr_valid),.wr_ready(fifo_wr_ready),.wr_level(fifo_level),
    .rd_clk(clk),.rd_rst(reset),.rd_data(fifo_rd_data),.rd_valid(frame_valid),.rd_ready(frame_ready));
  assign frame_last=fifo_rd_data[133];assign frame_bytes=fifo_rd_data[132:128];
  // Full formatter frames are big-endian wires; a final partial frame uses
  // the low N bytes. Normalize in SYS, outside the 200MHz capture path.
  wire [7:0] align_shift=({3'd0,(5'd16-frame_bytes)}<<3);
  wire [127:0] aligned=fifo_rd_data[127:0]<<align_shift;
  genvar b;generate for(b=0;b<16;b=b+1)begin: byte_order
    assign frame_data[b*8+:8]=aligned[(15-b)*8+:8];
  end endgenerate
  always @(posedge ref_clk or posedge ref_reset[1])
    if(ref_reset[1])begin
      command_sync<=0;stop_sync<=0;ready_sync<=0;seen_command<=0;state<=WAIT_COMMAND;
      drain<=0;ticks_ref<=0;stop_reason_ref<=0;observed_ref<=0;dropped_ref<=0;parser_ref<=0;
      sync_ref<=0;highwater_ref<=0;ready_losses_ref<=0;previous_ready<=0;finished_ref<=0;
    end else begin
      command_sync<={command_sync[1:0],command_epoch};stop_sync<={stop_sync[0],stop_request};
      ready_sync<={ready_sync[0],receiver_ready};previous_ready<=ready_sync[1];
      if(stop_sync[0])stop_reason_ref<=stop_reason==0 ? 2'd3 : stop_reason;
      if(capture_frame)begin observed_ref<=observed_ref+1'b1;if(!fifo_wr_ready)dropped_ref<=dropped_ref+1'b1;end
      if(parser_enable && source_parser_error)parser_ref<=parser_ref+1'b1;
      if(parser_enable && source_sync_event)sync_ref<=sync_ref+1'b1;
      if(parser_enable && fifo_level>highwater_ref)highwater_ref<=fifo_level;
      if(parser_enable && previous_ready && !ready_sync[1])ready_losses_ref<=ready_losses_ref+1'b1;
      case(state)
        WAIT_COMMAND:if(command_sync[2]!=seen_command)begin seen_command<=command_sync[2];state<=SETTLE;end
        SETTLE:begin ticks_ref<=ticks_held;state<=CLEAR_PARSER;end
        CLEAR_PARSER:state<=START_WINDOW;
        START_WINDOW:state<=WAIT_OPEN;
        WAIT_OPEN:if(window_open)state<=RUN;else if(window_done)begin state<=DRAIN;drain<=3;end
        RUN:if(window_done)begin state<=DRAIN;drain<=3;end
        DRAIN:if(drain==0)state<=EOF_WAIT;else drain<=drain-1'b1;
        EOF_WAIT:if(fifo_wr_ready)begin state<=FINISHED;finished_ref<=1;end
        default:state<=FINISHED;
      endcase
    end
  (* ASYNC_REG="TRUE" *) reg [1:0] finished_sync,active_sync;
  reg [1:0] settle_snapshot;
  assign source_active=active_sync[1];
  always @(posedge clk or posedge reset)
    if(reset)begin
      finished_sync<=0;active_sync<=0;settle_snapshot<=0;snapshot_valid<=0;
      elapsed_ticks<=0;observed_frames<=0;dropped_frames<=0;parser_errors<=0;sync_count<=0;
      frame_highwater<=0;ready_losses<=0;tail_bytes<=0;tail_ambiguous<=0;reason<=0;
    end else begin
      finished_sync<={finished_sync[0],finished_ref};active_sync<={active_sync[0],window_open};
      if(finished_sync[1] && !snapshot_valid)begin
        if(settle_snapshot!=3)settle_snapshot<=settle_snapshot+1'b1;
        else begin
          snapshot_valid<=1;elapsed_ticks<=elapsed_ref;observed_frames<=observed_ref;dropped_frames<=dropped_ref;
          parser_errors<=parser_ref;sync_count<=sync_ref;frame_highwater<=highwater_ref;ready_losses<=ready_losses_ref;
          tail_bytes<=source_tail_bytes;tail_ambiguous<=source_tail_ambiguous;
          reason<=window_rejected && stop_sync[1] ? stop_reason_ref : reason_ref;
        end
      end
    end
endmodule
