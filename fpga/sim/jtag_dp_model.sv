`timescale 1ns/1ps
// Independent ADIv5 TAP/DP model: JTAG response belongs to the PREVIOUS
// accepted transaction. ACK 010 means OK/FAULT; errors are in CTRL/STAT.
// This is a protocol model, not the Cortex-M3 processor model.
module jtag_dp_model #(parameter IRLEN=4,parameter DUMMY=0,parameter real RETURN_NS=0)(
    input wire rst_n,tck,tms,tdi,output reg tdo=1
);
    localparam RESET=0,IDLE=1,SEL_DR=2,CAP_DR=3,SHIFT_DR=4,EXIT1_DR=5,PAUSE_DR=6,EXIT2_DR=7,UPDATE_DR=8,
               SEL_IR=9,CAP_IR=10,SHIFT_IR=11,EXIT1_IR=12,PAUSE_IR=13,EXIT2_IR=14,UPDATE_IR=15;
    reg [3:0] state=RESET;
    reg [IRLEN-1:0] ir=14,ir_shift=0;
    reg [34:0] dr_shift=0;
    reg [2:0] captured_ack=2;
    reg [31:0] response=0,select_reg=0,csw=0,tar=0,rdbuff=0,ctrlstat=0;
    reg [31:0] mem[0:8191];
    integer scans=0,ap_reads=0,ap_writes=0,wait_scans=0;
    reg fault_next=0;
    wire bypass=(&ir);
    wire [7:0] apaddr={select_reg[7:4],dr_shift[2:1],2'b00};
    wire [31:0] write_value=dr_shift[34:3];
    function [3:0] next_state(input [3:0] s,input b);
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
    always @(negedge tck) begin
        if(state==SHIFT_IR) tdo<=#(RETURN_NS) ir_shift[0];
        else if(state==SHIFT_DR) tdo<=#(RETURN_NS) dr_shift[0];
        else tdo<=#(RETURN_NS) 1;
    end
    always @(posedge tck or negedge rst_n) begin
        if(!rst_n) begin state<=RESET;ir<=14;response<=0;captured_ack<=2;end
        else begin
            state<=next_state(state,tms);
            case(state)
            RESET: begin ir<=14;captured_ack<=2;end
            CAP_IR: ir_shift<=1;
            SHIFT_IR: ir_shift<={tdi,ir_shift[IRLEN-1:1]};
            UPDATE_IR: ir<=ir_shift;
            CAP_DR: begin
                scans<=scans+1;
                if(ir==14) dr_shift<={3'd0,32'h4ba00477};
                else if(bypass || DUMMY) dr_shift<=0;
                else begin
                    captured_ack<=wait_scans>0 ? 1 : 2;
                    dr_shift<={response,wait_scans>0 ? 3'd1 : 3'd2};
                    if(wait_scans>0) wait_scans<=wait_scans-1;
                end
            end
            SHIFT_DR: if(ir==14) dr_shift<={3'd0,tdi,dr_shift[31:1]};
                      else if(bypass || DUMMY) dr_shift<={34'd0,tdi};
                      else dr_shift<={tdi,dr_shift[34:1]};
            UPDATE_DR: if(!DUMMY) begin
                // DPv0 JTAG ABORT has DAPABORT only. Unlike SWD, sticky flags
                // are cleared by write-one-to-clear CTRL/STAT fields.
                if(ir==8) begin response<=0;end
                else if((ir==10 || ir==11) && captured_ack==2) begin
                    if(ir==10) begin
                        if(dr_shift[0]) case(dr_shift[2:1])
                        1:response<=ctrlstat;
                        2:response<=select_reg;
                        3:response<=0; // JTAG RDBUFF is RAZ; scan captures prior response.
                        default:response<=0;
                        endcase
                        else case(dr_shift[2:1])
                        1:ctrlstat<=(write_value & ~32'ha2) | ((write_value & 32'h50000000)<<1) | ((ctrlstat & 32'ha2) & ~write_value);
                        2:select_reg<=write_value;
                        default: ;
                        endcase
                    end else if(!(ctrlstat & 32'h20)) begin
                        if(fault_next) begin ctrlstat<=ctrlstat|32'h20;response<=0;fault_next<=0;end
                        else if(dr_shift[0]) begin
                            case(apaddr)
                            0:begin response<=csw;rdbuff<=csw;end
                            4:begin response<=tar;rdbuff<=tar;end
                            12:begin
                                response<=mem[tar[14:2]];rdbuff<=mem[tar[14:2]];ap_reads<=ap_reads+1;
                                if(csw[5:4]==1) tar<={tar[31:10],tar[9:0]+10'd4};
                            end
                            252:begin response<=32'h24770011;rdbuff<=32'h24770011;end
                            default:begin response<=0;rdbuff<=0;end
                            endcase
                        end else begin
                            ap_writes<=ap_writes+1;
                            case(apaddr)
                            0:csw<=write_value;
                            4:tar<=write_value;
                            12:begin mem[tar[14:2]]<=write_value;if(csw[5:4]==1) tar<={tar[31:10],tar[9:0]+10'd4};end
                            default: ;
                            endcase
                        end
                    end else response<=0;
                end
            end
            endcase
        end
    end
endmodule
