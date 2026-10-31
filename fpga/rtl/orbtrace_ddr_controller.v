`timescale 1ns/1ps
// DDR path bring-up: explicit address-dependent pattern source into the same
// bounded writer intended for ETM. No trace-source capability is advertised yet.
// USB configuration/reset has no connection to this hardware state machine.
module orbtrace_ddr_controller(
  (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi:m_axi, ASSOCIATED_RESET rst_n" *)
  input wire clk,input wire rst_n,
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
  reg [31:0] base_address,byte_limit,seed,capture_id,elapsed_cycles;
  reg active,done_sticky,error_sticky,rejected;
  reg writer_start,writer_abort;
  wire writer_busy,writer_done,writer_error,writer_rejected;
  wire [3:0] writer_error_code;wire [31:0] accepted_bytes,response_bytes;
  wire stream_ready;wire [31:0] remaining;
  wire [31:0] word_index=accepted_bytes>>2;
  wire [63:0] stream_data={32'hddaa0000 ^ seed ^ (word_index+32'd1),32'hddaa0000 ^ seed ^ word_index};
  wire [7:0] stream_keep=remaining>=8 ? 8'hff : (9'd1<<remaining[3:0])-1'b1;
  wire stream_last=remaining<=8;
  wire stream_valid=active && writer_busy && remaining!=0;
  assign m_axi_awcache=4'b0011;assign m_axi_awprot=0;assign m_axi_awlock=0;assign m_axi_awqos=0;
  orbtrace_ddr_writer writer(.clk(clk),.rst_n(rst_n),.start(writer_start),.abort(writer_abort),.finish_empty(1'b0),
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
      base_address<=32'h10000000;byte_limit<=0;seed<=0;capture_id<=0;elapsed_cycles<=0;
      active<=0;done_sticky<=0;error_sticky<=0;rejected<=0;writer_start<=0;writer_abort<=0;
    end else begin
      writer_start<=0;writer_abort<=0;
      if(s_axi_awvalid && s_axi_awready)begin aw_pending<=1;write_address<=s_axi_awaddr;end
      if(s_axi_wvalid && s_axi_wready)begin w_pending<=1;write_data<=s_axi_wdata;write_strobe<=s_axi_wstrb;end
      if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
      if(s_axi_rvalid && s_axi_rready)s_axi_rvalid<=0;
      if(active && elapsed_cycles!=32'hffffffff)elapsed_cycles<=elapsed_cycles+1'b1;
      if(writer_done)begin active<=0;done_sticky<=1;error_sticky<=writer_error;rejected<=rejected|writer_rejected;end
      if(write_commit)begin
        aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
        if(write_strobe!=4'hf || write_address[1:0]!=0)begin s_axi_bresp<=2;rejected<=1;end
        else case(write_address[7:2])
          1:begin
            if(write_data==1 && !active)begin
              writer_start<=1;active<=1;done_sticky<=0;error_sticky<=0;rejected<=0;
              elapsed_cycles<=0;capture_id<=capture_id+1'b1;
            end else if(write_data==2 && active)writer_abort<=1;
            else begin rejected<=1;s_axi_bresp<=2;end
          end
          3:if(!active)base_address<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          4:if(!active)byte_limit<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          5:if(!active)seed<=write_data;else begin rejected<=1;s_axi_bresp<=2;end
          default:begin rejected<=1;s_axi_bresp<=2;end
        endcase
      end
      if(s_axi_arvalid && s_axi_arready)begin
        s_axi_rvalid<=1;
        case(s_axi_araddr[7:2])
          0:s_axi_rdata<=32'h45444d31; // EDM1: DDR memory path, not ETM capture capability.
          1:s_axi_rdata<=0;
          2:s_axi_rdata<={27'd0,writer_busy,rejected,error_sticky,done_sticky,active};
          3:s_axi_rdata<=base_address;
          4:s_axi_rdata<=byte_limit;
          5:s_axi_rdata<=seed;
          6:s_axi_rdata<=accepted_bytes;
          7:s_axi_rdata<=response_bytes;
          8:s_axi_rdata<=elapsed_cycles;
          9:s_axi_rdata<={28'd0,writer_error_code};
          10:s_axi_rdata<=capture_id;
          11:s_axi_rdata<=3; // Pattern generator + bounded AXI writer. No trace-source bit.
          12:s_axi_rdata<=32'h10000000;
          13:s_axi_rdata<=32'h30000000;
          14:s_axi_rdata<=128;
          15:s_axi_rdata<=1; // address-dependent pattern, little endian 64-bit words.
          default:s_axi_rdata<=0;
        endcase
      end
    end
endmodule
