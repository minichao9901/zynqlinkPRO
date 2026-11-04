`timescale 1ns/1ps
// Bounded pattern or normalized framed-TPIU capture into the verified HP1 writer.
// Trace capability is explicit and enabled only with the matching RAW4 tap.
// USB configuration/reset has no connection to this hardware state machine.
module orbtrace_ddr_controller #(
  parameter ENABLE_TRACE_SOURCE=0,PREPARE_TIMEOUT=1000000,
  parameter [31:0] REGION_BASE=32'h39c00000,REGION_END=32'h40000000,
  parameter integer FIXED_CAPTURE_BYTES=104857600
)(
  (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi:m_axi, ASSOCIATED_RESET rst_n" *)
  input wire clk,input wire rst_n,
  (* X_INTERFACE_PARAMETER="FREQ_HZ 200000000" *) input wire ref_clk,
  input wire trace_ready,trace_idle,trace_receiver_ready_ref,
  input wire [127:0] trace_frame,trace_tail,input wire [4:0] trace_tail_bytes,
  input wire trace_frame_event,trace_parser_error,trace_sync_event,trace_tail_ambiguous,
  output reg trace_hold,output reg trace_prepare,
  output wire trace_sampler_gate,trace_parser_enable,trace_parser_clear,
  input wire [7:0] s_axi_awaddr,input wire [2:0] s_axi_awprot,
  input wire s_axi_awvalid,output wire s_axi_awready,
  input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
  input wire s_axi_wvalid,output wire s_axi_wready,
  output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
  input wire [7:0] s_axi_araddr,input wire [2:0] s_axi_arprot,
  input wire s_axi_arvalid,output wire s_axi_arready,
  output reg [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,
  output reg s_axi_rvalid,input wire s_axi_rready,
  (* X_INTERFACE_PARAMETER="PROTOCOL AXI4, READ_WRITE_MODE WRITE_ONLY, MAX_BURST_LENGTH 16, NUM_WRITE_OUTSTANDING 1" *)
  output wire [31:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
  output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,
  output wire [3:0] m_axi_awcache,output wire [2:0] m_axi_awprot,
  output wire m_axi_awlock,output wire [3:0] m_axi_awqos,
  output wire m_axi_awvalid,input wire m_axi_awready,
  output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,
  output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
  input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready
);
  reg aw_pending,w_pending;
  reg [7:0] write_address;reg [31:0] write_data;reg [3:0] write_strobe;
  reg [31:0] base_address,byte_limit,seed,capture_id,elapsed_cycles,requested_ticks;
  // Only two legal modes exist. Store the decoded two-bit value explicitly:
  // a 32-bit equality on software write_data otherwise survives synthesis
  // and fans into every writer byte-budget and RAM-enable path.
  reg [1:0] mode,record_mode;
  reg flight_trigger;
  reg [31:0] result_elapsed_high,result_trigger_ticks,result_trigger_high;
  reg result_triggered;
  wire flight_mode=mode==3;
  wire [63:0] writer_total;
  wire [31:0] writer_offset;
  wire ring_wrapped=writer_total>{32'd0,byte_limit};
  wire [31:0] rounded_offset=(writer_offset+15)&32'hfffffff0;
  wire [31:0] ring_oldest=ring_wrapped ? (rounded_offset>=byte_limit ? 0 : rounded_offset) : 0;
  wire [31:0] ring_trim=writer_offset[3:0]==0 ? 0 : 16-{28'd0,writer_offset[3:0]};
  wire [31:0] ring_bytes=ring_wrapped ? byte_limit-ring_trim : response_bytes;
  reg [63:0] nonce,capture_nonce;
  reg active,done_sticky,error_sticky,rejected;
  reg writer_start,writer_abort;
  reg [2:0] trace_phase;
  reg [31:0] prepare_wait;
  reg writer_epoch_valid;
  reg [3:0] controller_error;
  reg capture_start,capture_stop,writer_retired,discard_frames,eof_consumed;
  reg [1:0] capture_stop_reason;
  reg [31:0] result_ticks,result_frames,result_drops,result_parser,result_sync,result_highwater,result_ready_losses;
  reg [4:0] result_tail;
  reg [1:0] result_reason;
  reg result_ambiguous,capacity_reached;
  wire writer_busy,writer_done,writer_error,writer_rejected;
  wire [3:0] writer_error_code;wire [31:0] accepted_bytes,response_bytes;
  wire stream_ready;wire [31:0] remaining;
  wire [31:0] word_index=accepted_bytes>>2;
  wire [63:0] pattern_data={32'hddaa0000 ^ seed ^ (word_index+32'd1),32'hddaa0000 ^ seed ^ word_index};
  wire [7:0] pattern_keep=remaining>=8 ? 8'hff : (9'd1<<remaining[3:0])-1'b1;
  wire [127:0] capture_frame_data;
  wire [4:0] capture_frame_bytes;
  wire capture_frame_last,capture_frame_valid,capture_frame_ready,capture_active,capture_snapshot;
  wire [31:0] capture_ticks,capture_frames,capture_drops,capture_parser,capture_sync,capture_highwater,capture_ready_losses;
  wire [4:0] capture_tail;
  wire [1:0] capture_reason;
  wire capture_ambiguous;
  wire [31:0] capture_elapsed_high,capture_trigger_ticks,capture_trigger_high;
  wire capture_triggered;
  reg packet_start;
  wire [63:0] packet_data;wire [7:0] packet_keep;
  wire packet_last,packet_valid,packet_busy,packet_done,packet_empty,packet_rejected,packet_error,packet_limit,packet_frame_ready;
  wire [31:0] packet_input_bytes,packet_stream_bytes;
  wire trace_mode=ENABLE_TRACE_SOURCE && mode[1];
  wire [63:0] stream_data=trace_mode ? packet_data : pattern_data;
  wire [7:0] stream_keep=trace_mode ? packet_keep : pattern_keep;
  wire stream_last=trace_mode ? packet_last : remaining<=8;
  wire stream_valid=trace_mode ? packet_valid : active && writer_busy && remaining!=0;
  generate if(ENABLE_TRACE_SOURCE)begin: framed_capture
    orbtrace_ddr_capture capture(.clk(clk),.ref_clk(ref_clk),.rst_n(rst_n),.hold(trace_hold),
      .flight_mode(flight_mode),.trigger_request(flight_trigger),
      .start(capture_start),.requested_ticks(requested_ticks),.stop_request(capture_stop),.stop_reason(capture_stop_reason),
      .source_frame(trace_frame),.source_tail(trace_tail),.source_tail_bytes(trace_tail_bytes),
      .source_frame_event(trace_frame_event),.source_parser_error(trace_parser_error),.source_sync_event(trace_sync_event),
      .source_tail_ambiguous(trace_tail_ambiguous),.receiver_ready(trace_receiver_ready_ref),
      .sampler_gate(trace_sampler_gate),.parser_enable(trace_parser_enable),.parser_clear(trace_parser_clear),
      .frame_data(capture_frame_data),.frame_bytes(capture_frame_bytes),.frame_last(capture_frame_last),
      .frame_valid(capture_frame_valid),.frame_ready(capture_frame_ready),.source_active(capture_active),.snapshot_valid(capture_snapshot),
      .elapsed_ticks(capture_ticks),.observed_frames(capture_frames),.dropped_frames(capture_drops),.parser_errors(capture_parser),
      .sync_count(capture_sync),.frame_highwater(capture_highwater),.ready_losses(capture_ready_losses),
      .tail_bytes(capture_tail),.tail_ambiguous(capture_ambiguous),.reason(capture_reason),
      .elapsed_high(capture_elapsed_high),.trigger_ticks(capture_trigger_ticks),
      .trigger_high(capture_trigger_high),.triggered(capture_triggered));
    orbtrace_ddr_packetizer #(.FIXED_CAPACITY_BYTES(FIXED_CAPTURE_BYTES)) packetizer(.clk(clk),.rst(!rst_n || !trace_hold),.start(packet_start),.byte_limit(byte_limit),
      .ring_enable(flight_mode),
      .busy(packet_busy),.done(packet_done),.empty(packet_empty),.command_rejected(packet_rejected),
      .protocol_error(packet_error),.limit_reached(packet_limit),.frame_data(capture_frame_data),
      .frame_bytes(capture_frame_bytes),.frame_last(capture_frame_last),.frame_valid(capture_frame_valid && !discard_frames),
      .frame_ready(packet_frame_ready),.m_axis_tdata(packet_data),.m_axis_tkeep(packet_keep),.m_axis_tlast(packet_last),
      .m_axis_tvalid(packet_valid),.m_axis_tready(stream_ready),.input_bytes(packet_input_bytes),.stream_bytes(packet_stream_bytes));
    assign capture_frame_ready=discard_frames || packet_frame_ready;
  end else begin: pattern_only
    assign trace_sampler_gate=0;assign trace_parser_enable=0;assign trace_parser_clear=0;
    assign capture_active=0;assign capture_snapshot=0;assign capture_ticks=0;assign capture_frames=0;
    assign capture_drops=0;assign capture_parser=0;assign capture_sync=0;assign capture_highwater=0;assign capture_ready_losses=0;
    assign capture_tail=0;assign capture_reason=0;assign capture_ambiguous=0;
    assign capture_elapsed_high=0;assign capture_trigger_ticks=0;assign capture_trigger_high=0;assign capture_triggered=0;
    assign packet_data=0;assign packet_keep=0;assign packet_last=0;assign packet_valid=0;assign packet_busy=0;
    assign packet_done=0;assign packet_empty=0;assign packet_rejected=0;assign packet_error=0;assign packet_limit=0;
    assign packet_frame_ready=0;
    assign packet_input_bytes=0;assign packet_stream_bytes=0;
    assign capture_frame_data=0;assign capture_frame_bytes=0;assign capture_frame_last=0;assign capture_frame_valid=0;
    assign capture_frame_ready=0;
  end endgenerate
  assign m_axi_awcache=4'b0011;assign m_axi_awprot=0;assign m_axi_awlock=0;assign m_axi_awqos=0;
  orbtrace_ddr_writer #(.REGION_BASE(REGION_BASE),.REGION_END(REGION_END)) writer(.clk(clk),.rst_n(rst_n),.start(writer_start),.abort(writer_abort),.finish_empty(trace_mode && packet_done && packet_empty),
    .ring_enable(flight_mode),.total_committed(writer_total),.ring_offset(writer_offset),
    .base_address(base_address),.byte_limit(byte_limit),.busy(writer_busy),.done(writer_done),.error(writer_error),
    .error_code(writer_error_code),.command_rejected(writer_rejected),.accepted_bytes(accepted_bytes),.response_bytes(response_bytes),.remaining_bytes(remaining),
    .s_axis_tdata(stream_data),.s_axis_tkeep(stream_keep),.s_axis_tlast(stream_last),.s_axis_tvalid(stream_valid),.s_axis_tready(stream_ready),
    .m_axi_awaddr(m_axi_awaddr),.m_axi_awlen(m_axi_awlen),.m_axi_awsize(m_axi_awsize),.m_axi_awburst(m_axi_awburst),
    .m_axi_awvalid(m_axi_awvalid),.m_axi_awready(m_axi_awready),.m_axi_wdata(m_axi_wdata),.m_axi_wstrb(m_axi_wstrb),
    .m_axi_wlast(m_axi_wlast),.m_axi_wvalid(m_axi_wvalid),.m_axi_wready(m_axi_wready),
    .m_axi_bresp(m_axi_bresp),.m_axi_bvalid(m_axi_bvalid),.m_axi_bready(m_axi_bready));
  assign s_axi_awready=!aw_pending && !s_axi_bvalid;
  assign s_axi_wready=!w_pending && !s_axi_bvalid;
  assign s_axi_arready=!s_axi_rvalid;assign s_axi_rresp=0;
  wire write_commit=aw_pending && w_pending && !s_axi_bvalid;
  always @(posedge clk or negedge rst_n)
    if(!rst_n)begin
      aw_pending<=0;w_pending<=0;write_address<=0;write_data<=0;write_strobe<=0;
      s_axi_bvalid<=0;s_axi_bresp<=0;s_axi_rvalid<=0;s_axi_rdata<=0;
      base_address<=REGION_BASE;byte_limit<=0;seed<=0;capture_id<=0;elapsed_cycles<=0;
      active<=0;done_sticky<=0;error_sticky<=0;rejected<=0;writer_start<=0;writer_abort<=0;
      mode<=1;record_mode<=1;requested_ticks<=0;nonce<=0;capture_nonce<=0;trace_hold<=0;trace_prepare<=0;trace_phase<=0;prepare_wait<=0;
      capture_start<=0;capture_stop<=0;capture_stop_reason<=0;writer_retired<=0;discard_frames<=0;packet_start<=0;eof_consumed<=0;
      writer_epoch_valid<=0;controller_error<=0;
      result_ticks<=0;result_frames<=0;result_drops<=0;result_parser<=0;result_sync<=0;result_highwater<=0;
      result_ready_losses<=0;result_tail<=0;result_reason<=0;result_ambiguous<=0;capacity_reached<=0;
      flight_trigger<=0;result_elapsed_high<=0;result_trigger_ticks<=0;result_trigger_high<=0;result_triggered<=0;
    end else begin
      writer_start<=0;writer_abort<=0;capture_start<=0;trace_prepare<=0;packet_start<=0;
      if(s_axi_awvalid && s_axi_awready)begin aw_pending<=1;write_address<=s_axi_awaddr;end
      if(s_axi_wvalid && s_axi_wready)begin w_pending<=1;write_data<=s_axi_wdata;write_strobe<=s_axi_wstrb;end
      if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
      if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
      if(active && elapsed_cycles!=32'hffffffff)elapsed_cycles<=elapsed_cycles+1'b1;
      if(writer_start)writer_epoch_valid<=1;
      if(trace_mode && capture_frame_valid && capture_frame_ready && capture_frame_last)eof_consumed<=1;
      if(writer_done)begin
        writer_retired<=1;error_sticky<=error_sticky|writer_error;rejected<=rejected|writer_rejected;
        if(!trace_mode || trace_phase!=3)begin active<=0;done_sticky<=1;trace_hold<=0;trace_phase<=0;end
      end
      if(active && trace_mode)case(trace_phase)
        1:begin
          prepare_wait<=prepare_wait+1'b1;
          if(prepare_wait>=4 && trace_ready)begin trace_hold<=1;trace_phase<=2;end
          else if(prepare_wait>=PREPARE_TIMEOUT)begin
            active<=0;done_sticky<=1;error_sticky<=1;controller_error<=6;result_reason<=3;trace_phase<=0;
          end
        end
        2:begin writer_start<=1;packet_start<=1;trace_phase<=4;end
        4:if(writer_busy)begin capture_start<=1;trace_phase<=3;end
        3:begin
          if(packet_limit)begin capture_stop<=1;capture_stop_reason<=2;discard_frames<=1;capacity_reached<=1;end
          if(packet_error || (writer_done && writer_error))begin
            capture_stop<=1;capture_stop_reason<=3;discard_frames<=1;error_sticky<=1;
            if(packet_error && writer_busy)writer_abort<=1;
          end
          if(writer_retired && capture_snapshot && eof_consumed)begin
            result_ticks<=capture_ticks;result_frames<=capture_frames;result_drops<=capture_drops;
            result_elapsed_high<=capture_elapsed_high;result_trigger_ticks<=capture_trigger_ticks;
            result_trigger_high<=capture_trigger_high;result_triggered<=capture_triggered;
            result_parser<=capture_parser;result_sync<=capture_sync;result_highwater<=capture_highwater;
            result_ready_losses<=capture_ready_losses;
            // Fixed-capacity records end on a complete formatter frame.
            // Any source tail observed during stop/CDC drain was discarded
            // and must not relabel the final stored full frame as partial.
            result_tail<=(capacity_reached && FIXED_CAPTURE_BYTES!=0) ? 0 : capture_tail;
            result_reason<=capture_reason;
            result_ambiguous<=(capacity_reached && FIXED_CAPTURE_BYTES!=0) ? 0 : capture_ambiguous;
            error_sticky<=error_sticky || capture_drops!=0 || capture_parser!=0 || capture_ready_losses!=0 || capture_sync==0 || response_bytes==0 || (capacity_reached && FIXED_CAPTURE_BYTES==0);
            active<=0;done_sticky<=1;trace_hold<=0;trace_phase<=0;
          end
        end
        5:if(writer_busy)writer_abort<=1;
        default:begin end
      endcase
      if(write_commit)begin
        aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
        if(write_strobe!=4'hf || write_address[1:0]!=0)begin s_axi_bresp<=2;rejected<=1;end
        else case(write_address[7:2])
          1:begin
            if(write_data==1 && !active && (!trace_mode || (trace_idle && requested_ticks!=0)))begin
              writer_start<=!trace_mode;active<=1;done_sticky<=0;error_sticky<=0;rejected<=0;
              elapsed_cycles<=0;capture_id<=capture_id+1'b1;
              capture_nonce<=nonce;record_mode<=mode;
              flight_trigger<=0;result_elapsed_high<=0;result_trigger_ticks<=0;result_trigger_high<=0;result_triggered<=0;
              writer_retired<=0;capture_stop<=0;capture_stop_reason<=0;discard_frames<=0;capacity_reached<=0;eof_consumed<=0;
              writer_epoch_valid<=0;controller_error<=0;
              result_ticks<=0;result_frames<=0;result_drops<=0;result_parser<=0;result_sync<=0;result_highwater<=0;
              result_ready_losses<=0;result_tail<=0;result_reason<=0;result_ambiguous<=0;
              if(trace_mode)begin
                if(FIXED_CAPTURE_BYTES!=0 && !flight_mode)begin base_address<=REGION_BASE;byte_limit<=FIXED_CAPTURE_BYTES;end
                trace_prepare<=1;prepare_wait<=0;trace_phase<=1;
              end
            end else if(write_data==4 && active && flight_mode && trace_phase==3 && !flight_trigger)begin
              flight_trigger<=1;
            end else if(write_data==2 && active)begin
              if(trace_mode)begin
                capture_stop<=1;capture_stop_reason<=1;
                if(trace_phase==1)begin active<=0;done_sticky<=1;result_reason<=1;trace_phase<=0;end
                else if(trace_phase!=3)begin capture_start<=0;trace_phase<=5;result_reason<=1;end
              end else writer_abort<=1;
            end
            else begin rejected<=1;s_axi_bresp<=2;end
          end
          3:if(!active)base_address<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          4:if(!active)byte_limit<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          5:if(!active)seed<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          15:if(!active && (write_data==1 || (ENABLE_TRACE_SOURCE && (write_data==2 || write_data==3))))mode<=write_data[1:0];else begin rejected<=1;s_axi_bresp<=2;end
          16:if(!active)requested_ticks<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          31:if(!active)nonce[31:0]<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          32:if(!active)nonce[63:32]<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          default:begin rejected<=1;s_axi_bresp<=2;end
        endcase
      end
      if(s_axi_arvalid && s_axi_arready)begin
        s_axi_rvalid<=1;
        case(s_axi_araddr[7:2])
          0:s_axi_rdata<=32'h45444d31; // EDM1: DDR memory path, not ETM capture capability.
          1:s_axi_rdata<=0;
          2:s_axi_rdata<={26'd0,capture_active,writer_busy,rejected,error_sticky,done_sticky,active};
          3:s_axi_rdata<=base_address;
          4:s_axi_rdata<=byte_limit;
          5:s_axi_rdata<=seed;
          6:s_axi_rdata<=writer_epoch_valid ? (record_mode==3 && done_sticky ? ring_bytes : accepted_bytes) : 0;
          7:s_axi_rdata<=writer_epoch_valid ? (record_mode==3 ? ring_bytes : response_bytes) : 0;
          8:s_axi_rdata<=elapsed_cycles;
          9:s_axi_rdata<=controller_error!=0 ? {28'd0,controller_error} : (writer_epoch_valid ? {28'd0,writer_error_code} : 0);
          10:s_axi_rdata<=capture_id;
          11:s_axi_rdata<=3 | (ENABLE_TRACE_SOURCE ? 32'h104 : 0);
          12:s_axi_rdata<=REGION_BASE;
          13:s_axi_rdata<=REGION_END;
          14:s_axi_rdata<=128;
          15:s_axi_rdata<=mode;
          16:s_axi_rdata<=requested_ticks;
          17:s_axi_rdata<=result_ticks;
          18:s_axi_rdata<={27'd0,(done_sticky && record_mode[1] && (!writer_epoch_valid || response_bytes==0)),
            (result_sync==0 && record_mode[1]),(result_ready_losses!=0),(result_parser!=0),(result_drops!=0)};
          19:s_axi_rdata<=result_drops;
          20:s_axi_rdata<=result_parser;
          21:s_axi_rdata<=result_frames;
          22:s_axi_rdata<={27'd0,result_tail};
          23:s_axi_rdata<={30'd0,result_reason};
          24:s_axi_rdata<=result_sync;
          25:s_axi_rdata<=result_highwater;
          26:s_axi_rdata<=result_ready_losses;
          27:s_axi_rdata<={31'd0,capacity_reached};
          28:s_axi_rdata<=record_mode[1] ? 32'h46524d31 : 32'h50415431; // FRM1 or PAT1.
          29:s_axi_rdata<={31'd0,result_ambiguous};
          30:s_axi_rdata<=trace_phase;
          31:s_axi_rdata<=capture_nonce[31:0];
          32:s_axi_rdata<=capture_nonce[63:32];
          33:s_axi_rdata<=record_mode;
          34:s_axi_rdata<=32'h31525246; // FRR1 extension, only capability bit8 authorizes reads.
          35:s_axi_rdata<=ring_oldest;
          36:s_axi_rdata<=ring_bytes;
          37:s_axi_rdata<=writer_total[31:0];
          38:s_axi_rdata<=writer_total[63:32];
          39:s_axi_rdata<=result_trigger_ticks;
          40:s_axi_rdata<=result_trigger_high;
          41:s_axi_rdata<=result_elapsed_high;
          42:s_axi_rdata<={28'd0,flight_trigger,ring_wrapped,result_triggered,(record_mode==3)};
          43:s_axi_rdata<=requested_ticks;
          default:s_axi_rdata<=0;
        endcase
      end
    end
endmodule
