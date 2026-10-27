`timescale 1ns/1ps
// Extended timing bank: writes stage, reads return active configuration.
// Only an idle, validated COMMIT changes the running timing configuration.
module swd_timing_regs (
    input wire clk,rst_n,quiescent,wr,
    input wire [7:0] addr,raddr,
    input wire [31:0] wdata,legacy_cfg,
    input wire [3:0] wstrb,
    output reg [31:0] rdata,
    output wire [31:0] control,xfer_half_q,swj_half_q,ack_sample,data_sample,
    output wire [31:0] ack_half_q,turn_half_q,
    output wire legacy_apply,output wire [31:0] legacy_value
);
    reg [31:0] active[0:6],shadow[0:7];
    reg [15:0] epoch;
    reg [7:0] error_code;
    integer i,j;
    wire [31:0] ack_q = shadow[5]==0 ? shadow[1] : shadow[5];
    reg [7:0] invalid;
    always @* begin
        invalid=0;
        if(shadow[0]&32'hfffffffe)invalid=2;
        else if(shadow[1]<65536 || shadow[2]<65536 ||
                (shadow[5]!=0 && shadow[5]<65536) ||
                (shadow[6]!=0 && shadow[6]<65536))invalid=3;
        else if((shadow[3]&32'hfff80000)!=0 ||
                (!shadow[3][16] && shadow[3][15:0]>=ack_q[31:16]))invalid=4;
        else if((shadow[4]&32'hfff80000)!=0 ||
                (!shadow[4][16] && shadow[4][15:0]>=shadow[1][31:16]))invalid=5;
        else if((shadow[7]&32'hf07c000e)!=0)invalid=6;
    end
    wire commit = wr && addr==8'hf0 && wstrb[0] && wdata==1;
    assign legacy_apply=commit && quiescent && invalid==0;
    assign legacy_value=shadow[7];
    assign control=active[0];assign xfer_half_q=active[1];assign swj_half_q=active[2];
    assign ack_sample=active[3];assign data_sample=active[4];
    assign ack_half_q=active[5];assign turn_half_q=active[6];
    always @* begin
        rdata=0;
        if(raddr>=8'hd0 && raddr<=8'he8)rdata=active[(raddr-8'hd0)>>2];
        else case(raddr)
            8'hec:rdata=legacy_cfg;
            8'hf4:rdata={epoch, error_code,7'd0,!quiescent};
            8'hf8:rdata=32'h53575431; // SWT1
            default:;
        endcase
    end
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            active[0]<=0;shadow[0]<=0;
            active[1]<=65536;shadow[1]<=65536;
            active[2]<=393216;shadow[2]<=393216;
            active[3]<=65536;shadow[3]<=65536;
            active[4]<=65536;shadow[4]<=65536;
            active[5]<=0;shadow[5]<=0;active[6]<=0;shadow[6]<=0;
            shadow[7]<=32'h00020a01;epoch<=0;error_code<=0;
        end else if(wr)begin
            if(addr>=8'hd0 && addr<=8'hec)begin
                for(j=0;j<4;j=j+1)if(wstrb[j])
                    shadow[(addr-8'hd0)>>2][j*8+:8]<=wdata[j*8+:8];
            end else if(addr==8'hf0 && wstrb[0])begin
                if(wdata==2)begin
                    for(i=0;i<7;i=i+1)shadow[i]<=active[i];
                    shadow[7]<=legacy_cfg;error_code<=0;
                end else if(wdata==1 || wdata==4)begin
                    if(!quiescent)error_code<=1;
                    else if(wdata==4)begin
                        active[0]<=0;shadow[0]<=0;epoch<=epoch+1'b1;error_code<=0;
                    end else if(invalid!=0)error_code<=invalid;
                    else begin
                        for(i=0;i<7;i=i+1)active[i]<=shadow[i];
                        epoch<=epoch+1'b1;error_code<=0;
                    end
                end else error_code<=7;
            end
        end
    end
endmodule
