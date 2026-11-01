`timescale 1ns/1ps
// Bounded AXIS64 -> AXI write master. Two 16-beat banks overlap filling and
// bus service. One outstanding burst, <=128B, never crosses a 4KiB boundary.
// response_bytes advances only on OKAY B handshake; memory readback/cache
// acceptance is a separate gate. Abort drains an issued AW/W/B transaction.
module orbtrace_ddr_writer #(
  parameter [31:0] REGION_BASE=32'h10000000,
  parameter [31:0] REGION_END=32'h30000000
)(
  input wire clk,input wire rst_n,
  input wire start,input wire abort,input wire finish_empty,
  input wire [31:0] base_address,input wire [31:0] byte_limit,
  output reg busy,output reg done,output reg error,
  output reg [3:0] error_code,output reg command_rejected,
  output reg [31:0] accepted_bytes,response_bytes,remaining_bytes,
  input wire [63:0] s_axis_tdata,input wire [7:0] s_axis_tkeep,
  input wire s_axis_tlast,input wire s_axis_tvalid,output wire s_axis_tready,
  output reg [31:0] m_axi_awaddr,output wire [7:0] m_axi_awlen,
  output wire [2:0] m_axi_awsize,output wire [1:0] m_axi_awburst,
  output wire m_axi_awvalid,input wire m_axi_awready,
  output wire [63:0] m_axi_wdata,output wire [7:0] m_axi_wstrb,
  output wire m_axi_wlast,output wire m_axi_wvalid,input wire m_axi_wready,
  input wire [1:0] m_axi_bresp,input wire m_axi_bvalid,output wire m_axi_bready
);
  localparam IDLE=0,ADDRESS=1,DATA=2,RESPONSE=3;
  reg [1:0] state;
  (* ram_style="distributed" *) reg [63:0] data_bank[0:31];
  (* ram_style="distributed" *) reg [7:0] keep_bank[0:31];
  reg [1:0] bank_ready,bank_last;
  reg [4:0] bank_count[0:1];
  reg [7:0] bank_bytes[0:1];
  reg producer_bank,reader_bank,input_closed,aborting;
  reg [3:0] fill_index,send_index;
  reg [7:0] fill_bytes,burst_bytes;
  reg [4:0] burst_beats;
  reg burst_last;
  reg [31:0] limit,next_address;
  function [3:0] byte_count(input [7:0] keep);
    // The interface accepts only contiguous low-byte masks. Decode them
    // directly instead of a general eight-input population-count adder.
    // Invalid masks return zero and are rejected before any state/RAM write.
    begin case(keep)
      8'h01:byte_count=1;8'h03:byte_count=2;8'h07:byte_count=3;8'h0f:byte_count=4;
      8'h1f:byte_count=5;8'h3f:byte_count=6;8'h7f:byte_count=7;8'hff:byte_count=8;
      default:byte_count=0;
    endcase end
  endfunction
  wire [3:0] incoming_bytes=byte_count(s_axis_tkeep);
  wire legal_keep=incoming_bytes!=0 &&
                  (s_axis_tlast || s_axis_tkeep==8'hff);
  // Registered remaining budget avoids a 32-bit add then 33-bit compare on
  // every RAM write-enable. Each beat is <=8B, so the guard needs only the
  // low nibble unless any higher bit is set.
  wire has_room=(|remaining_bytes[31:4]) || remaining_bytes[3:0]>=incoming_bytes;
  wire at_limit=remaining_bytes==incoming_bytes;
  wire input_fire=s_axis_tvalid && s_axis_tready;
  wire valid_beat=legal_keep && has_room && (!at_limit || s_axis_tlast);
  wire [32:0] end_address={1'b0,base_address}+{1'b0,byte_limit};
  wire legal_config=base_address[6:0]==0 && base_address>=REGION_BASE && byte_limit!=0 &&
                    end_address<={1'b0,REGION_END};
  assign s_axis_tready=busy && !input_closed && !aborting && !abort && !bank_ready[producer_bank];
  assign m_axi_awlen={3'd0,burst_beats}-8'd1;
  assign m_axi_awsize=3;assign m_axi_awburst=1;
  assign m_axi_awvalid=state==ADDRESS;
  assign m_axi_wdata=data_bank[{reader_bank,send_index}];
  assign m_axi_wstrb=keep_bank[{reader_bank,send_index}];
  assign m_axi_wlast={1'b0,send_index}+5'd1==burst_beats;
  assign m_axi_wvalid=state==DATA;
  assign m_axi_bready=state==RESPONSE;
  // Keep payload storage outside the asynchronous state-reset process so
  // Vivado can infer simple dual-port distributed RAM instead of reset FFs.
  always @(posedge clk)
    if(rst_n && input_fire && valid_beat)begin
      data_bank[{producer_bank,fill_index}]<=s_axis_tdata;
      keep_bank[{producer_bank,fill_index}]<=s_axis_tkeep;
    end
  always @(posedge clk or negedge rst_n)
    if(!rst_n)begin
      busy<=0;done<=0;error<=0;error_code<=0;command_rejected<=0;
      accepted_bytes<=0;response_bytes<=0;remaining_bytes<=0;state<=IDLE;bank_ready<=0;bank_last<=0;
      bank_count[0]<=0;bank_count[1]<=0;bank_bytes[0]<=0;bank_bytes[1]<=0;
      producer_bank<=0;reader_bank<=0;input_closed<=0;aborting<=0;
      fill_index<=0;send_index<=0;fill_bytes<=0;burst_bytes<=0;burst_beats<=0;burst_last<=0;
      limit<=0;next_address<=0;m_axi_awaddr<=0;
    end else begin
      done<=0;
      if(start)begin
        if(busy || state!=IDLE)command_rejected<=1;
        else if(!legal_config)begin
          command_rejected<=1;error<=1;error_code<=1;done<=1;accepted_bytes<=0;response_bytes<=0;remaining_bytes<=0;
        end
        else begin
          busy<=1;error<=0;error_code<=0;command_rejected<=0;aborting<=0;
          limit<=byte_limit;remaining_bytes<=byte_limit;next_address<=base_address;
          accepted_bytes<=0;response_bytes<=0;bank_ready<=0;bank_last<=0;
          producer_bank<=0;reader_bank<=0;input_closed<=0;fill_index<=0;fill_bytes<=0;
        end
      end
      if(abort && busy)begin aborting<=1;error<=1;if(!error)error_code<=5;end
      if(input_fire)begin
        if(!valid_beat)begin
          aborting<=1;error<=1;error_code<=!legal_keep ? 2 : 3;
        end else begin
          accepted_bytes<=accepted_bytes+incoming_bytes;
          remaining_bytes<=remaining_bytes-incoming_bytes;
          if(fill_index==15 || s_axis_tlast)begin
            bank_count[producer_bank]<={1'b0,fill_index}+5'd1;
            bank_bytes[producer_bank]<=fill_bytes+incoming_bytes;
            bank_last[producer_bank]<=s_axis_tlast;
            bank_ready[producer_bank]<=1;producer_bank<=!producer_bank;
            fill_index<=0;fill_bytes<=0;
          end else begin fill_index<=fill_index+1'b1;fill_bytes<=fill_bytes+incoming_bytes;end
          if(s_axis_tlast)input_closed<=1;
        end
      end
      case(state)
        IDLE:if(busy)begin
          if(aborting || abort)begin busy<=0;done<=1;bank_ready<=0;end
          else if(finish_empty && accepted_bytes==0 && bank_ready==0 && !s_axis_tvalid)begin
            busy<=0;done<=1;input_closed<=1;
          end else if(bank_ready[reader_bank])begin
            m_axi_awaddr<=next_address;burst_beats<=bank_count[reader_bank];
            burst_bytes<=bank_bytes[reader_bank];burst_last<=bank_last[reader_bank];
            send_index<=0;state<=ADDRESS;
          end
        end
        ADDRESS:if(m_axi_awready)state<=DATA;
        DATA:if(m_axi_wready)begin
          if(m_axi_wlast)state<=RESPONSE;else send_index<=send_index+1'b1;
        end
        RESPONSE:if(m_axi_bvalid)begin
          state<=IDLE;bank_ready[reader_bank]<=0;reader_bank<=!reader_bank;
          if(m_axi_bresp!=0)begin busy<=0;done<=1;error<=1;error_code<=4;bank_ready<=0;end
          else begin
            response_bytes<=response_bytes+burst_bytes;
            next_address<=next_address+({27'd0,burst_beats}<<3);
            if(burst_last || aborting || abort)begin busy<=0;done<=1;bank_ready<=0;end
          end
        end
      endcase
    end
endmodule
