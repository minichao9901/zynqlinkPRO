`timescale 1ns/1ps
// Parallel ETM -> PS MMIO record FIFO. Each 16-bit record is {0,sourceID,data}.
// Separate AW/W capture supports independent AXI-Lite channel arrival.
module orbtrace_controller #(
  parameter C_S_AXI_DATA_WIDTH=32,
  parameter C_S_AXI_ADDR_WIDTH=6,
  parameter FIFO_ADDR_BITS=12
)(
  (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET rst_n" *)
  input wire clk,input wire rst_n,
  (* X_INTERFACE_PARAMETER="FREQ_HZ 200000000" *)
  input wire ref_clk,
  input wire trace_clk,input wire [3:0] trace_data,
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,input wire [2:0] s_axi_awprot,
  input wire s_axi_awvalid,output wire s_axi_awready,
  input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
  input wire s_axi_wvalid,output wire s_axi_wready,
  output wire [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
  input wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,input wire [2:0] s_axi_arprot,
  input wire s_axi_arvalid,output wire s_axi_arready,
  output reg [31:0] s_axi_rdata,output wire [1:0] s_axi_rresp,
  output reg s_axi_rvalid,input wire s_axi_rready
);
  reg enable;
  reg [1:0] width;
  reg [5:0] clear_count;
  wire trace_clock,trace_io_clock;
  // Keep pad sampling on the dedicated bank clock tree, rather than a BUFG
  // whose insertion delay creates an input hold violation on this interface.
  BUFIO trace_io_buffer(.I(trace_clk),.O(trace_io_clock));
  BUFR #(.BUFR_DIVIDE("BYPASS"),.SIM_DEVICE("7SERIES")) trace_clock_buffer(
    .I(trace_clk),.CE(1'b1),.CLR(1'b0),.O(trace_clock));
  wire delay_ref_clock,delay_ready,delay_calibrated;
  (* ASYNC_REG="TRUE" *) reg [1:0] delay_ready_sync;
  BUFG delay_reference_buffer(.I(ref_clk),.O(delay_ref_clock));
  (* IODELAY_GROUP="ORBTRACE_INPUTS" *)
  IDELAYCTRL delay_control(.REFCLK(delay_ref_clock),.RST(!rst_n || clear_count!=0),.RDY(delay_calibrated));
  always @(posedge clk or negedge rst_n)
    if(!rst_n)delay_ready_sync<=0;else delay_ready_sync<={delay_ready_sync[0],delay_calibrated};
  assign delay_ready=delay_ready_sync[1];
  wire [7:0] byte_data;
  wire [6:0] source_id;
  wire byte_valid,receiver_synced,receiver_overflow;
  wire [FIFO_ADDR_BITS:0] level;
  wire fifo_full=level==(1<<FIFO_ADDR_BITS);
  wire receiver_reset=!rst_n || !enable || clear_count!=0 || !delay_ready;
  orbtrace_parallel #(.USE_IO_CLOCK(1),.USE_INPUT_DELAY(1)) receiver(.trace_clk(trace_clock),.trace_io_clk(trace_io_clock),.trace_data(trace_data),.width(width),
    .clk(clk),.rst(receiver_reset),.data(byte_data),.channel(source_id),
    .valid(byte_valid),.ready(!fifo_full && !receiver_reset),
    .synced(receiver_synced),.overflow(receiver_overflow));
  (* ram_style="block" *) reg [15:0] records[0:(1<<FIFO_ADDR_BITS)-1];
  reg [FIFO_ADDR_BITS:0] write_ptr,read_ptr;
  reg [31:0] total;
  reg lost,seen_sync;
  assign level=write_ptr-read_ptr;
  reg aw_pending,w_pending;
  reg [C_S_AXI_ADDR_WIDTH-1:0] write_address;
  reg [31:0] write_data;
  reg [3:0] write_strobe;
  assign s_axi_awready=!aw_pending && !s_axi_bvalid;
  assign s_axi_wready=!w_pending && !s_axi_bvalid;
  assign s_axi_arready=!s_axi_rvalid && !read_fifo;
  assign s_axi_bresp=0;
  assign s_axi_rresp=0;
  wire write_commit=aw_pending && w_pending && !s_axi_bvalid;
  wire clear=write_commit && write_address[5:2]==1 && write_strobe[0] && write_data[1];
  wire read_accept=s_axi_arvalid && s_axi_arready;
  wire pop=read_accept && s_axi_araddr[5:2]==4 && level!=0 && clear_count==0 && !clear;
  wire push=byte_valid && !fifo_full && !receiver_reset;
  // Memory has a synchronous read port so Vivado infers block RAM.
  reg [15:0] read_record;
  reg read_fifo;
  always @(posedge clk)begin
    if(pop)read_record<=records[read_ptr[FIFO_ADDR_BITS-1:0]];
    if(push)records[write_ptr[FIFO_ADDR_BITS-1:0]]<={1'b0,source_id,byte_data};
  end
  always @(posedge clk or negedge rst_n)
    if(!rst_n)begin
      enable<=0;width<=3;clear_count<=32;write_ptr<=0;read_ptr<=0;
      total<=0;lost<=0;seen_sync<=0;aw_pending<=0;w_pending<=0;
      write_address<=0;write_data<=0;write_strobe<=0;
      s_axi_bvalid<=0;s_axi_rvalid<=0;s_axi_rdata<=0;read_fifo<=0;
    end else begin
      if(clear_count!=0)clear_count<=clear_count-1'b1;
      if(s_axi_awvalid && s_axi_awready)begin aw_pending<=1;write_address<=s_axi_awaddr;end
      if(s_axi_wvalid && s_axi_wready)begin w_pending<=1;write_data<=s_axi_wdata;write_strobe<=s_axi_wstrb;end
      if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
      if(write_commit)begin
        aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;
        if(write_address[5:2]==1 && write_strobe[0])begin
          enable<=write_data[0];
          // Width changes are accepted only with an explicit fresh capture.
          if(write_data[1] || !enable)width<=write_data[3:2];
        end
      end
      if(clear)begin
        clear_count<=32;write_ptr<=0;read_ptr<=0;total<=0;lost<=0;seen_sync<=0;
      end else begin
        if(push)begin write_ptr<=write_ptr+1'b1;total<=total+1'b1;end
        if(pop)read_ptr<=read_ptr+1'b1;
        if(receiver_overflow || (seen_sync && enable && !delay_ready))lost<=1;
        if(receiver_synced)seen_sync<=1;
      end
      if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
      // A FIFO data read needs one extra cycle for the BRAM output.
      if(read_fifo)begin s_axi_rdata<={16'd0,read_record};s_axi_rvalid<=1;read_fifo<=0;end
      if(read_accept && !read_fifo)begin
        s_axi_rvalid<=1;
        case(s_axi_araddr[5:2])
          0:s_axi_rdata<=32'h45544d31;
          1:s_axi_rdata<={28'd0,width,1'b0,enable};
          2:s_axi_rdata<={28'd0,delay_ready,lost,seen_sync,enable};
          3:s_axi_rdata<=level;
          4:begin
            if(pop)begin read_fifo<=1;s_axi_rvalid<=0;end
            else s_axi_rdata<=32'h80000000;
          end
          5:s_axi_rdata<=total;
          6:s_axi_rdata<=120000000;
          7:s_axi_rdata<=(1<<FIFO_ADDR_BITS);
          default:s_axi_rdata<=0;
        endcase
      end
    end
endmodule
