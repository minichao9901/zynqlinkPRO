`timescale 1ns/1ps
// Simulation-first Zynq-7 parallel TRACE frontend. width is ORBTrace's encoding:
// 1 = one pin, 2 = two pins, 3 = four pins. Hold it stable until next reset.
// The consumer receives unformatted bytes tagged with CoreSight source ID.
// No USB/ORBFlow framing is added here.
module orbtrace_parallel #(parameter USE_IO_CLOCK=0,USE_INPUT_DELAY=0) (
    input wire trace_clk,input wire [3:0] trace_data,input wire [1:0] width,
    input wire trace_io_clk,
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
        IDELAYE2 #(.DELAY_SRC("IDATAIN"),.IDELAY_TYPE("FIXED"),.IDELAY_VALUE(28),
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
    wire [127:0] frame;
    wire toggle,trace_synced;
    reg previous_toggle;
    always @(posedge trace_clk or posedge rst)
      if(rst)previous_toggle<=0;else previous_toggle<=toggle;
    orbtrace_traceif receiver(.rst(trace_reset[1]),.traceDina(rise),.traceDinb(fall),
      .traceClkin(trace_clk),.width(width),.edgeOutput(),.FrAvail(toggle),.Frame(frame),.synced(trace_synced));
    wire [127:0] fifo_data;
    wire fifo_valid,fifo_ready,trace_overflow;
    orbtrace_frame_fifo fifo(.wr_clk(trace_clk),.wr_rst(trace_reset[1]),
      .wr_data(frame),.wr_valid(toggle!=previous_toggle),.overflow(trace_overflow),
      .rd_clk(clk),.rd_rst(sys_reset[1]),.rd_data(fifo_data),.rd_valid(fifo_valid),.rd_ready(fifo_ready));
    (* ASYNC_REG="TRUE" *) reg [1:0] sync_status,overflow_status;
    always @(posedge clk or posedge rst)
      if(rst)begin sync_status<=0;overflow_status<=0;end
      else begin sync_status<={sync_status[0],trace_synced};overflow_status<={overflow_status[0],trace_overflow};end
    assign synced=sync_status[1];assign overflow=overflow_status[1];
    orbtrace_tpiu_demux demux(.clk(clk),.rst(sys_reset[1]),.frame(fifo_data),.frame_valid(fifo_valid),
      .frame_ready(fifo_ready),.data(data),.channel(channel),.valid(valid),.ready(ready));
endmodule
