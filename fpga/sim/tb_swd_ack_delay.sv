`timescale 1ns/1ps
// Wire-level ACK timing model. The target updates ACK on SWCLK rising edges,
// with a configurable output delay. WAIT (010) makes a late response visible
// even while SWDIO has its pull-up.
module tb_swd_ack_delay #(
  parameter integer CLK_HALF_NS = 5,
  parameter integer TARGET_TCO_NS = 1,
  parameter integer ACK_DELAY = 0,
  parameter integer TURN_EXTRA = 0,
  parameter integer RX_BOUNDARY = 1,
  parameter integer EXPECT_ACK = 2
);
  reg clk=0; always #(CLK_HALF_NS) clk=~clk;
  reg rst_n=0, start=0;
  wire [31:0] rdata;
  wire [2:0] ack;
  wire parity_err, busy;
  wire swclk, swdio_o, swdio_t;
  tri1 swdio;
  reg target_oe=0, target_out=1;
  reg delayed_oe=0, delayed_out=1;
  assign swdio = swdio_t ? 1'bz : swdio_o;
  assign swdio = delayed_oe ? delayed_out : 1'bz;
  always @(target_oe or target_out) begin
    delayed_oe <= #(TARGET_TCO_NS) target_oe;
    delayed_out <= #(TARGET_TCO_NS) target_out;
  end
  reg sample_fall=0;
  always @(negedge clk) sample_fall <= swdio;

  swd_core core(.rx_boundary(1'(RX_BOUNDARY)),
    .next_valid(1'b0),.next_request(8'd0),.next_wdata(32'd0),.next_ready(),.result_valid(),
    .clk(clk), .rst_n(rst_n), .start(start), .mode(1'b1),
    .timestamp_en(1'b0), .idle_cycles(4'd0), .data_phase(1'b0),
    .clock_delay(4'd0), .delay_fast(4'd0),
    .turn_extra(2'(TURN_EXTRA)), .ack_delay(3'(ACK_DELAY)),
    .swj_data(256'd0), .swj_count(8'd0),
    .xfer_request(8'h02), .xfer_wdata(32'd0),
    .xfer_rdata(rdata), .ack(ack), .parity_err(parity_err),
    .busy(busy), .timestamp(), .swclk(swclk), .swdio_o(swdio_o),
    .swdio_i(swdio), .swdio_i_fall(sample_fall), .swdio_t(swdio_t));

  initial begin
    #50; rst_n=1;
    @(negedge clk); start=1;
    @(negedge clk); start=0;

    // Launch ACK0 on the request-turnaround rise, as the real ARM target
    // does. Every following rise consumes the current bit and launches next.
    wait(core.state == 4'd3);
    @(posedge swclk);
    target_oe <= 1'b1;
    target_out <= EXPECT_ACK[0];
    @(posedge swclk); target_out <= EXPECT_ACK[1];
    @(posedge swclk); target_out <= EXPECT_ACK[2];
    @(posedge swclk); target_oe <= 1'b0;

    wait(!busy);
    $display("RESULT ack=%b delay=%0d turn=%0d tco=%0d",ack,ACK_DELAY,TURN_EXTRA,TARGET_TCO_NS);
    if (ack !== EXPECT_ACK[2:0]) $fatal(1,"ACK failed");
    $display("PASS");
    $finish;
  end
  initial begin #100000; $fatal(1,"timeout"); end
endmodule
