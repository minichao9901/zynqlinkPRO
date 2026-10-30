`timescale 1ns/1ps
// Simulation-first Zynq-7 parallel TRACE frontend. width is ORBTrace's encoding:
// 1 = one pin, 2 = two pins, 3 = four pins. Hold it stable until next reset.
// The consumer receives unformatted bytes tagged with CoreSight source ID.
// No USB/ORBFlow framing is added here.
module orbtrace_parallel #(parameter USE_IO_CLOCK=0,USE_INPUT_DELAY=0,INPUT_DELAY_VALUE=16,RAW_DIAGNOSTIC=0) (
    input wire trace_clk,input wire [3:0] trace_data,input wire [1:0] width,
    input wire trace_io_clk,input wire trace_pad_clk,input wire sample_clk,
    input wire clk,input wire rst,
    output wire [7:0] data,output wire [6:0] channel,
    output wire valid,input wire ready,
    output wire synced,output wire overflow
);
    (* ASYNC_REG="TRUE" *) reg [1:0] trace_reset,sys_reset;
    always @(posedge trace_clk or posedge rst)
      if(rst)trace_reset<=3;else trace_reset<={trace_reset[0],1'b0};
    always @(posedge clk or posedge rst)
      if(rst)sys_reset<=3;else sys_reset<={sys_reset[0],1'b0};
    wire [3:0] rise,fall;
    genvar i;
    generate for(i=0;i<4;i=i+1)begin: capture
      wire sampled_data;
      if(USE_INPUT_DELAY)begin: delay_input
        (* IODELAY_GROUP="ORBTRACE_INPUTS" *)
        IDELAYE2 #(.DELAY_SRC("IDATAIN"),.IDELAY_TYPE("FIXED"),.IDELAY_VALUE(INPUT_DELAY_VALUE),
          .REFCLK_FREQUENCY(200.0),.HIGH_PERFORMANCE_MODE("TRUE"),.SIGNAL_PATTERN("DATA")) input_delay(
          .IDATAIN(trace_data[i]),.DATAIN(1'b0),.DATAOUT(sampled_data),.C(1'b0),.CE(1'b0),
          .INC(1'b0),.LD(1'b0),.LDPIPEEN(1'b0),.REGRST(1'b0),.CINVCTRL(1'b0),
          .CNTVALUEIN(5'd0),.CNTVALUEOUT());
      end else begin assign sampled_data=trace_data[i];end
      // In the board design BUFIO samples the pads and BUFR clocks fabric.
      // Pipeline both DDR halves together before their related-clock transfer.
      IDDR #(.DDR_CLK_EDGE(USE_IO_CLOCK ? "SAME_EDGE_PIPELINED" : "OPPOSITE_EDGE"),.SRTYPE("ASYNC")) ddr (
        .C(USE_IO_CLOCK ? trace_io_clk : trace_clk),.CE(1'b1),.D(sampled_data),.R(trace_reset[1]),.S(1'b0),.Q1(rise[i]),.Q2(fall[i]));
    end endgenerate
    wire [127:0] frame,decoded_frame;
    wire toggle,decoded_toggle,trace_synced,oversample_synced,parser_malformed;
    wire capture_clk,capture_reset;
    reg previous_toggle;
    always @(posedge capture_clk or posedge rst)
      if(rst)previous_toggle<=0;else previous_toggle<=toggle;
    generate if(RAW_DIAGNOSTIC!=2)begin: formatted_receiver
      orbtrace_traceif receiver(.rst(trace_reset[1]),.traceDina(rise),.traceDinb(fall),
        .traceClkin(trace_clk),.width(width),.edgeOutput(),.FrAvail(decoded_toggle),.Frame(decoded_frame),.synced(trace_synced));
    end else begin: oversample_receiver_bypass
      assign decoded_toggle=1'b0;
      assign decoded_frame=128'd0;
      assign trace_synced=1'b0;
    end endgenerate
    generate if(RAW_DIAGNOSTIC==2)begin: raw_oversample
      // Diagnostic, low-frequency mode only: synchronize the five physical
      // pins to the independent 200 MHz reference and require two consecutive
      // clock samples before accepting an edge. Each accepted edge samples
      // the matching delayed data; no CDC exception applies to the normal IDDR.
      (* ASYNC_REG="TRUE" *) reg [1:0] sample_reset;
      (* ASYNC_REG="TRUE" *) reg [4:0] pad_meta,pad_sync;
      reg [1:0] clock_history;
      reg stable_clock,half;
      reg [3:0] low_nibble,count;
      reg [7:0] sampled_byte;
      reg byte_toggle;
      wire [127:0] parsed_frame;
      wire parsed_toggle,parsed_synced;
      wire edge_rise=(clock_history==2'b11 && !stable_clock);
      wire edge_fall=(clock_history==2'b00 && stable_clock);
      always @(posedge sample_clk or posedge rst)
        if(rst)sample_reset<=3;else sample_reset<={sample_reset[0],1'b0};
      always @(posedge sample_clk or posedge sample_reset[1])
        if(sample_reset[1])begin
          pad_meta<=0;pad_sync<=0;clock_history<=0;stable_clock<=0;half<=0;
          low_nibble<=0;sampled_byte<=0;byte_toggle<=0;
        end else begin
          pad_meta<={trace_pad_clk,trace_data};
          pad_sync<=pad_meta;
          clock_history<={clock_history[0],pad_sync[4]};
          if(edge_rise || edge_fall)begin
            stable_clock<=edge_rise;
            half<=!half;
            if(!half)low_nibble<=pad_sync[3:0];
            else begin
              sampled_byte<={pad_sync[3:0],low_nibble};
              byte_toggle<=!byte_toggle;
            end
          end
        end
      orbtrace_tpiu_stream parser(.clk(sample_clk),.rst(sample_reset[1]),
        .byte_in(sampled_byte),.byte_toggle(byte_toggle),
        .frame(parsed_frame),.frame_toggle(parsed_toggle),.synced(parsed_synced),.malformed(parser_malformed));
      assign frame=parsed_frame;
      assign toggle=parsed_toggle;
      assign capture_clk=sample_clk;
      assign capture_reset=sample_reset[1];
      assign oversample_synced=parsed_synced;
    end else if(RAW_DIAGNOSTIC==1)begin: raw_capture
      // Preserve every sampled DDR byte, including full/half sync. Frame
      // boundaries here are transport blocks, not TPIU formatter boundaries.
      reg [127:0] build_frame,completed_frame;
      reg [3:0] count;
      reg frame_toggle;
      always @(posedge trace_clk or posedge trace_reset[1])
        if(trace_reset[1])begin build_frame<=0;completed_frame<=0;count<=0;frame_toggle<=0;end
        else begin
          build_frame<={build_frame[119:0],fall,rise};
          count<=count+1'b1;
          if(count==15)begin completed_frame<={build_frame[119:0],fall,rise};frame_toggle<=!frame_toggle;end
        end
      assign frame=completed_frame;
      assign toggle=frame_toggle;
      assign capture_clk=trace_clk;
      assign capture_reset=trace_reset[1];
      assign oversample_synced=1'b0;
      assign parser_malformed=1'b0;
    end else begin: formatted_capture
      assign frame=decoded_frame;
      assign toggle=decoded_toggle;
      assign capture_clk=trace_clk;
      assign capture_reset=trace_reset[1];
      assign oversample_synced=1'b0;
      assign parser_malformed=1'b0;
    end endgenerate
    wire [127:0] fifo_data;
    wire fifo_valid,fifo_ready,trace_overflow;
    orbtrace_frame_fifo fifo(.wr_clk(capture_clk),.wr_rst(capture_reset),
      .wr_data(frame),.wr_valid(toggle!=previous_toggle),.overflow(trace_overflow),
      .rd_clk(clk),.rd_rst(sys_reset[1]),.rd_data(fifo_data),.rd_valid(fifo_valid),.rd_ready(fifo_ready));
    (* ASYNC_REG="TRUE" *) reg [1:0] sync_status,oversample_sync_status,overflow_status;
    always @(posedge clk or posedge rst)
      if(rst)begin sync_status<=0;oversample_sync_status<=0;overflow_status<=0;end
      else begin sync_status<={sync_status[0],trace_synced};
        oversample_sync_status<={oversample_sync_status[0],oversample_synced};
        overflow_status<={overflow_status[0],trace_overflow | parser_malformed};end
    assign synced=sync_status[1] | oversample_sync_status[1];assign overflow=overflow_status[1];
    generate if(RAW_DIAGNOSTIC==1)begin: raw_output
      reg [127:0] raw_frame;
      reg [3:0] index;
      reg active;
      assign data=raw_frame[127:120];
      assign channel=7'd2; // Diagnostic payload, not a CoreSight source ID.
      assign valid=active;
      assign fifo_ready=!active || (index==15 && ready);
      always @(posedge clk or posedge sys_reset[1])
        if(sys_reset[1])begin raw_frame<=0;index<=0;active<=0;end
        else if(fifo_ready && fifo_valid)begin raw_frame<=fifo_data;index<=0;active<=1;end
        else if(active && ready)begin
          if(index==15)active<=0;
          else begin raw_frame<={raw_frame[119:0],8'd0};index<=index+1'b1;end
        end
    end else begin: decoded_output
      orbtrace_tpiu_demux demux(.clk(clk),.rst(sys_reset[1]),.frame(fifo_data),.frame_valid(fifo_valid),
        .frame_ready(fifo_ready),.data(data),.channel(channel),.valid(valid),.ready(ready));
    end endgenerate
endmodule
