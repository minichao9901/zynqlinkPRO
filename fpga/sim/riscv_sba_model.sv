`timescale 1ns/1ps
// Standard 5-bit JTAG DTM, 41-bit DMI and 32-bit SBA memory model.
// Memory addressing deliberately permits the same SRAM plans as the ARM
// pipeline regression so transport changes can share its end-to-end checks.
module riscv_sba_model #(parameter real RETURN_NS=12)(
    input wire rst_n,tck,tms,tdi,output reg tdo=1
);
    localparam RESET=0,IDLE=1,SEL_DR=2,CAP_DR=3,SHIFT_DR=4,EXIT1_DR=5,
        PAUSE_DR=6,EXIT2_DR=7,UPDATE_DR=8,SEL_IR=9,CAP_IR=10,SHIFT_IR=11,
        EXIT1_IR=12,PAUSE_IR=13,EXIT2_IR=14,UPDATE_IR=15;
    reg [3:0] state=RESET;
    reg [4:0] ir=1,ir_shift=1;
    reg [40:0] dr=0,response=0;
    reg [31:0] sbcs=0,sbaddr=0,sbdata=0,dmcontrol=0;
    reg [31:0] mem[0:8191];
    reg fault_next=0;
    reg dmi_poisoned=0;
    wire [31:0] ctrlstat=sbcs[14:12]!=0 ? 32'ha2 : 0;
    integer scans=0,ir_writes=0,idles=0,dmi_scans=0;
    integer bus_reads=0,bus_writes=0,out_of_range_reads=0,mmio_reads=0,counter_reads=0;
    wire [6:0] address=dr[40:34];
    wire [31:0] data=dr[33:2];
    task bus_read(input [31:0] at);
        begin
            bus_reads<=bus_reads+1;
            if(at==32'hf0407000)begin counter_reads<=counter_reads+1;sbdata<=counter_reads+1;end
            else if(at[31:18]==14'h0041 || at[31:15]==17'h1e080)sbdata<=mem[at[14:2]];
            else if(at==32'h40010000)begin
                mmio_reads<=mmio_reads+1;sbdata<=mmio_reads+1;
            end else begin out_of_range_reads<=out_of_range_reads+1;sbdata<=0;end
        end
    endtask
    function [3:0] next_state(input [3:0] s,input b);
        case(s)
        RESET:next_state=b?RESET:IDLE;IDLE:next_state=b?SEL_DR:IDLE;
        SEL_DR:next_state=b?SEL_IR:CAP_DR;CAP_DR:next_state=b?EXIT1_DR:SHIFT_DR;
        SHIFT_DR:next_state=b?EXIT1_DR:SHIFT_DR;EXIT1_DR:next_state=b?UPDATE_DR:PAUSE_DR;
        PAUSE_DR:next_state=b?EXIT2_DR:PAUSE_DR;EXIT2_DR:next_state=b?UPDATE_DR:SHIFT_DR;
        UPDATE_DR:next_state=b?SEL_DR:IDLE;SEL_IR:next_state=b?RESET:CAP_IR;
        CAP_IR:next_state=b?EXIT1_IR:SHIFT_IR;SHIFT_IR:next_state=b?EXIT1_IR:SHIFT_IR;
        EXIT1_IR:next_state=b?UPDATE_IR:PAUSE_IR;PAUSE_IR:next_state=b?EXIT2_IR:PAUSE_IR;
        EXIT2_IR:next_state=b?UPDATE_IR:SHIFT_IR;UPDATE_IR:next_state=b?SEL_DR:IDLE;
        default:next_state=RESET;
        endcase
    endfunction
    always @(posedge tck or negedge rst_n)begin
        if(!rst_n)begin
            state<=RESET;ir<=1;ir_shift<=1;dr<=0;response<=0;sbcs<=0;
            sbaddr<=0;sbdata<=0;dmcontrol<=0;idles<=0;dmi_poisoned<=0;
        end else begin
            state<=next_state(state,tms);
            if(state==IDLE)idles<=idles+1;
            case(state)
            RESET:begin ir<=1;ir_shift<=1;dmi_poisoned<=0;end
            CAP_IR:ir_shift<=1;
            SHIFT_IR:ir_shift<={tdi,ir_shift[4:1]};
            UPDATE_IR:begin ir<=ir_shift;ir_writes<=ir_writes+1;end
            CAP_DR:begin
                scans<=scans+1;
                case(ir)
                1:begin dr<={9'd0,32'h1000563d};dmi_poisoned<=1;end
                16:begin dr<={9'd0,32'h7071};dmi_poisoned<=1;end
                17:dr<=dmi_poisoned ? 41'd1 : response;
                default:dr<=0;
                endcase
            end
            SHIFT_DR:begin
                if(ir==17)dr<={tdi,dr[40:1]};
                else if(ir==1 || ir==16)dr<={9'd0,tdi,dr[31:1]};
                else dr<=0;
            end
            UPDATE_DR:if(ir==17 && !dmi_poisoned)begin
                if(dmi_scans!=0 && idles<7)$fatal(1,"RISC-V DMI idle violation: %0d",idles);
                idles<=0;dmi_scans<=dmi_scans+1;
                response<=0;
                if(dr[1:0]==1)begin
                    case(address)
                    'h10:response<={address,dmcontrol,2'b00};
                    'h11:response<={address,32'h00400ca2,2'b00};
                    'h38:response<={address,(32'h20000407|sbcs),2'b00};
                    'h39:response<={address,sbaddr,2'b00};
                    'h3c:begin
                        response<={address,sbdata,2'b00};
                        if(sbcs[15])begin
                            bus_read(sbaddr);
                            if(sbcs[16])sbaddr<=sbaddr+4;
                        end
                    end
                    default:response<={address,32'd0,2'b00};
                    endcase
                end else if(dr[1:0]==2)begin
                    case(address)
                    'h10:dmcontrol<=data;
                    'h38:sbcs<=(data&32'h001f8000) | (sbcs&32'h00407000&~data);
                    'h39:begin
                        sbaddr<=data;
                        if(sbcs[20])begin
                            bus_read(data);
                            if(sbcs[16])sbaddr<=data+4;
                        end
                    end
                    'h3c:begin
                        bus_writes<=bus_writes+1;
                        mem[sbaddr[14:2]]<=data;
                        if(sbcs[16])sbaddr<=sbaddr+4;
                    end
                    default:;
                    endcase
                end
                if(fault_next && address=='h3c)begin
                    sbcs<=sbcs|32'h00002000;fault_next<=0;
                end
            end
            default:;
            endcase
        end
    end
    always @(negedge tck)begin
        if(state==SHIFT_IR)tdo<=#(RETURN_NS)ir_shift[0];
        else if(state==SHIFT_DR)tdo<=#(RETURN_NS)dr[0];
        else tdo<=#(RETURN_NS)1;
    end
endmodule
