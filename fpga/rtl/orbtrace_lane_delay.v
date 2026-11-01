`timescale 1ns/1ps
// Five physical-input delays (data[0..3], TRACECLK). Configuration is a
// bundled-data request/ack transaction. The payload stays fixed until ack;
// all IDELAY controls run from the independent, always-running 200MHz clock.
// No capture reset changes the selected taps. A failed load blocks capture.
module orbtrace_lane_delay (
  input wire clk,input wire rst_n,input wire ref_clk,input wire calibrated,
  input wire active,input wire apply,input wire malformed,
  input wire [25:0] requested,input wire [4:0] pads,
  output wire [4:0] sampled_pads,
  output wire ready,output wire ready_ref,output wire busy,
  output wire [31:0] status,output reg [25:0] applied,
  output reg [31:0] accepted,rejected,load_failures
);
  reg [25:0] payload;
  reg request_toggle;
  (* ASYNC_REG="TRUE" *) reg [1:0] acknowledge_sync,ready_sync,fault_sync,valid_sync,calibrated_sync,initialized_sync;
  reg acknowledged;
  reg acknowledge_ref;
  reg valid_ref,fault_ref,enabled_ref,initialized_ref;
  reg [24:0] readback_ref;
  assign busy=request_toggle!=acknowledge_sync[1];
  assign ready=!busy && ready_sync[1];
  assign status={16'd0,10'd0,(rejected!=0),fault_sync[1],valid_sync[1],ready,busy,applied[25]};
  always @(posedge clk or negedge rst_n)
    if(!rst_n)begin
      payload<=0;request_toggle<=0;acknowledge_sync<=0;ready_sync<=0;fault_sync<=0;valid_sync<=0;calibrated_sync<=0;
      initialized_sync<=0;acknowledged<=0;applied<=0;accepted<=0;rejected<=0;load_failures<=0;
    end else begin
      acknowledge_sync<={acknowledge_sync[0],acknowledge_ref};
      ready_sync<={ready_sync[0],ready_ref};fault_sync<={fault_sync[0],fault_ref};valid_sync<={valid_sync[0],valid_ref};
      calibrated_sync<={calibrated_sync[0],calibrated};
      initialized_sync<={initialized_sync[0],initialized_ref};
      if(malformed || (apply && (active || busy || !calibrated_sync[1] || !initialized_sync[1] || (!requested[25] && |requested[24:0]))))rejected<=rejected+1'b1;
      // A fresh explicit load can recover a readback failure while idle.
      if(apply && !malformed && !active && !busy && calibrated_sync[1] && initialized_sync[1] && (requested[25] || requested[24:0]==0))begin
        payload<=requested;request_toggle<=!request_toggle;accepted<=accepted+1'b1;
      end
      if(acknowledge_sync[1]!=acknowledged)begin
        acknowledged<=acknowledge_sync[1];applied<={enabled_ref,readback_ref};
        if(fault_ref)load_failures<=load_failures+1'b1;
      end
    end

  (* ASYNC_REG="TRUE" *) reg [1:0] request_sync;
  reg [25:0] captured;
  reg [2:0] state;
  reg load;
  wire [24:0] counts;
  wire [4:0] delayed;
  assign ready_ref=calibrated && valid_ref && !fault_ref && state==0 && request_sync[1]==acknowledge_ref;
  // One routable ILOGIC input path per pad. A fabric mux between IBUF and
  // IDELAY outputs creates partially routed nets in the 7-series implementation.
  // The disabled setting means explicitly loaded zero taps, not zero insertion.
  assign sampled_pads=delayed;
  always @(posedge ref_clk or negedge rst_n)
    if(!rst_n)begin
      request_sync<=0;captured<=0;state<=4;load<=0;
      acknowledge_ref<=0;valid_ref<=0;fault_ref<=0;enabled_ref<=0;readback_ref<=0;initialized_ref<=0;
    end else begin
      request_sync<={request_sync[0],request_toggle};load<=0;
      case(state)
        0:if(request_sync[1]!=acknowledge_ref)begin captured<=payload;state<=1;end
        1:begin
          if(calibrated)begin load<=1;state<=2;end
          else begin initialized_ref<=1;fault_ref<=1;valid_ref<=0;acknowledge_ref<=request_sync[1];state<=0;end
        end
        2:state<=3; // IDELAY sees LD at this edge; CNTVALUEOUT updates after it.
        3:begin
          initialized_ref<=1;
          readback_ref<=counts;
          if(calibrated && counts==captured[24:0])begin
            enabled_ref<=captured[25];valid_ref<=1;fault_ref<=0;
          end else begin valid_ref<=0;fault_ref<=1;end
          acknowledge_ref<=request_sync[1];state<=0;
        end
        4:if(calibrated)begin captured<=0;state<=1;end // Explicit startup LD, even for tap zero.
        default:begin initialized_ref<=1;fault_ref<=1;valid_ref<=0;state<=0;acknowledge_ref<=request_sync[1];end
      endcase
    end
  genvar i;
  generate for(i=0;i<5;i=i+1)begin: lane
    (* IODELAY_GROUP="ORBTRACE_INPUTS" *)
    IDELAYE2 #(.DELAY_SRC("IDATAIN"),.IDELAY_TYPE("VAR_LOAD"),.IDELAY_VALUE(0),
      .REFCLK_FREQUENCY(200.0),.HIGH_PERFORMANCE_MODE("TRUE"),.SIGNAL_PATTERN(i==4 ? "CLOCK" : "DATA")) delay(
      .IDATAIN(pads[i]),.DATAIN(1'b0),.DATAOUT(delayed[i]),.C(ref_clk),.CE(1'b0),
      .INC(1'b0),.LD(load),.LDPIPEEN(1'b0),.REGRST(1'b0),.CINVCTRL(1'b0),
      .CNTVALUEIN(captured[i*5+:5]),.CNTVALUEOUT(counts[i*5+:5]));
  end endgenerate
endmodule
