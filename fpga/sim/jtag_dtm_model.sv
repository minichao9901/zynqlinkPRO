`timescale 1ns/1ps
// Minimal RISC-V DTM (debug transport module) TAP model.
// IR is IRLEN bits. IDCODE (0x01) returns a 32-bit IDCODE register; every other
// instruction behaves as BYPASS (single zero bit), which is what an
// unimplemented instruction does on a real DTM. TDO is registered on the
// falling edge like a real TAP, so it is stable at the next rising edge.
module jtag_dtm_model #(parameter IRLEN=5, parameter [31:0] IDCODE=32'h1000563D,
                        parameter real RETURN_NS=0)(
    input wire rst_n, input wire tck, input wire tms, input wire tdi, output reg tdo=1
);
    localparam RESET=0,IDLE=1,SEL_DR=2,CAP_DR=3,SHIFT_DR=4,EXIT1_DR=5,PAUSE_DR=6,EXIT2_DR=7,UPDATE_DR=8,
               SEL_IR=9,CAP_IR=10,SHIFT_IR=11,EXIT1_IR=12,PAUSE_IR=13,EXIT2_IR=14,UPDATE_IR=15;
    reg [3:0] state=RESET;
    reg [IRLEN-1:0] ir=1, ir_shift=0;
    reg [31:0] dr=0;
    integer scans=0, ir_writes=0;
    function [3:0] next_state(input [3:0] s, input b);
        case(s)
        RESET:next_state=b?RESET:IDLE; IDLE:next_state=b?SEL_DR:IDLE;
        SEL_DR:next_state=b?SEL_IR:CAP_DR; CAP_DR:next_state=b?EXIT1_DR:SHIFT_DR;
        SHIFT_DR:next_state=b?EXIT1_DR:SHIFT_DR; EXIT1_DR:next_state=b?UPDATE_DR:PAUSE_DR;
        PAUSE_DR:next_state=b?EXIT2_DR:PAUSE_DR; EXIT2_DR:next_state=b?UPDATE_DR:SHIFT_DR;
        UPDATE_DR:next_state=b?SEL_DR:IDLE; SEL_IR:next_state=b?RESET:CAP_IR;
        CAP_IR:next_state=b?EXIT1_IR:SHIFT_IR; SHIFT_IR:next_state=b?EXIT1_IR:SHIFT_IR;
        EXIT1_IR:next_state=b?UPDATE_IR:PAUSE_IR; PAUSE_IR:next_state=b?EXIT2_IR:PAUSE_IR;
        EXIT2_IR:next_state=b?UPDATE_IR:SHIFT_IR; UPDATE_IR:next_state=b?SEL_DR:IDLE;
        default:next_state=RESET;
        endcase
    endfunction
    always @(posedge tck or negedge rst_n) begin
        if(!rst_n) begin
            state<=RESET; ir<=1'b1; ir_shift<=1'b1; dr<=0;
        end else begin
            state<=next_state(state,tms);
            case(state)
            RESET:     begin ir<={{(IRLEN-1){1'b0}},1'b1}; ir_shift<=1'b1; end
            CAP_IR:    ir_shift<=1'b1;
            SHIFT_IR:  ir_shift<={tdi,ir_shift[IRLEN-1:1]};
            UPDATE_IR: begin ir<=ir_shift; ir_writes<=ir_writes+1; end
            CAP_DR:    begin scans<=scans+1; dr<=(ir==1'b1) ? IDCODE : 32'd0; end
            SHIFT_DR:  if(ir==1'b1) dr<={tdi,dr[31:1]};
            default:   ;
            endcase
        end
    end
    always @(negedge tck or negedge rst_n) begin
        if(!rst_n) tdo<=1'b1;
        else case(state)
            SHIFT_IR: tdo<=#(RETURN_NS) ir_shift[0];
            SHIFT_DR: tdo<=#(RETURN_NS) (ir==1'b1) ? dr[0] : 1'b0;
            default:  tdo<=#(RETURN_NS) 1'b1;
        endcase
    end
endmodule
