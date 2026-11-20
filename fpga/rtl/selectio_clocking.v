`timescale 1ns/1ps
module selectio_clocking (
    (* X_INTERFACE_PARAMETER="FREQ_HZ 200000000" *) input wire ref_clk,
    input wire resetn, calibrated, jtag_hold, swd_hold, legacy_released,
    (* X_INTERFACE_PARAMETER="FREQ_HZ 200000000" *) output wire serial_clk,
    (* X_INTERFACE_PARAMETER="FREQ_HZ 100000000" *) output wire quad_clk,
    (* X_INTERFACE_PARAMETER="FREQ_HZ 50000000" *) output wire octet_clk,
    output wire phy_reset, jtag_reset, swd_reset, jtag_ready,
    output reg [1:0] owner = 0
);
    wire feedback, feedback_raw, locked, serial_raw, quad_raw, octet_raw;
    MMCME2_BASE #(.CLKIN1_PERIOD(5.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(5.0),
        .CLKOUT0_DIVIDE_F(5.0), .CLKOUT1_DIVIDE(10), .CLKOUT2_DIVIDE(20)) mmcm (
        .CLKIN1(ref_clk), .CLKFBIN(feedback), .CLKFBOUT(feedback_raw), .RST(!resetn),
        .PWRDWN(1'b0), .LOCKED(locked), .CLKOUT0(serial_raw), .CLKOUT1(quad_raw), .CLKOUT2(octet_raw)
    );
    BUFG feedback_buf(.I(feedback_raw), .O(feedback));
    BUFG serial_buf(.I(serial_raw), .O(serial_clk));
    BUFG quad_buf(.I(quad_raw), .O(quad_clk));
    BUFG octet_buf(.I(octet_raw), .O(octet_clk));

    wire reset_request = !resetn || !locked;
    (* ASYNC_REG="TRUE" *) reg [3:0] reset_pipe = 4'hf;
    always @(posedge quad_clk or posedge reset_request)
        if (reset_request) reset_pipe <= 4'hf;
        else reset_pipe <= {reset_pipe[2:0], 1'b0};
    assign phy_reset = reset_pipe[3];

    (* ASYNC_REG="TRUE" *) reg [3:0] meta = 0, synced = 0;
    wire [1:0] requested = !synced[2] ? 2'd1 :
                           synced[3] && synced[1:0]==2'b01 ? 2'd2 :
                           synced[3] && synced[1:0]==2'b10 ? 2'd3 : 2'd0;
    reg [2:0] park_count = 0;
    always @(posedge quad_clk) begin
        meta <= {calibrated, legacy_released, !swd_hold, !jtag_hold};
        synced <= meta;
        if (phy_reset) begin owner <= 0; park_count <= 0; end
        else if (owner != 0) begin
            // Another engine requesting the pins cannot interrupt a running
            // transfer. The AXI engines only accept HOLD at transaction end.
            if ((owner==1 && synced[2]) || (owner==2 && !synced[0]) ||
                (owner==3 && !synced[1])) begin owner <= 0; park_count <= 0; end
        end else if (park_count != 7) park_count <= park_count + 1'b1;
        else owner <= requested;
    end
    assign swd_reset = phy_reset || owner!=3;
    wire jreset_request = phy_reset || owner!=2;
    (* ASYNC_REG="TRUE" *) reg [2:0] jreset_pipe = 7;
    always @(posedge octet_clk or posedge jreset_request)
        if (jreset_request) jreset_pipe <= 7;
        else jreset_pipe <= {jreset_pipe[1:0], 1'b0};
    assign jtag_reset = jreset_pipe[2];
    assign jtag_ready = !jtag_reset;
endmodule
