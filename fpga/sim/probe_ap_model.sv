`timescale 1ns/1ps
// Clocked SWD transaction model, including real next_ready acceptance and
// AHB-AP posted reads. Changing data catches stale/shifted sample pipelines.
module probe_ap_model (
    input wire clk,rst_n,start,next_valid,chain_enable,
    input wire [7:0] req,next_req,input wire [31:0] wdata,
    output reg busy,result_valid,output wire next_ready,
    output reg [2:0] ack,output reg parity,output reg [31:0] rdata
);
    reg [7:0] current_req;
    reg [31:0] current_data,tar=0,csw=0,posted=0;
    reg [31:0] mem[0:8191];
    integer delay=0,reads=0,calls=0;
    reg inject_wait=0,inject_fault=0,inject_parity=0,hang=0;
    reg dynamic_data=0;
    assign next_ready=result_valid && ack==1 && !parity && chain_enable;
    always @(posedge clk) begin
        if(!rst_n) begin busy<=0;result_valid<=0;delay<=0;ack<=1;parity<=0;end
        else begin
            result_valid<=0;
            if(result_valid) begin
                if(next_ready && next_valid) begin
                    busy<=1;current_req<=next_req;current_data<=0;delay<=20;calls<=calls+1;
                end else busy<=0;
            end else if(start && !busy) begin
                busy<=1;current_req<=req;current_data<=wdata;delay<=20;calls<=calls+1;
            end else if(busy && !hang) begin
                if(delay!=0) delay<=delay-1;
                else begin
                    result_valid<=1;ack<=1;parity<=inject_parity;
                    if(inject_fault) ack<=4;
                    else if(inject_wait) begin ack<=2;inject_wait<=0;end
                    else case(current_req)
                    8'h08: if(current_data!=0) $fatal(1,"SELECT");
                    8'h01: csw<=current_data;
                    8'h05: tar<=current_data;
                    8'h0f: begin
                        rdata<=posted;posted<=dynamic_data ? reads : mem[tar[14:2]];reads<=reads+1;
                        if(csw[5:4]==1) tar<={tar[31:10],tar[9:0]+10'd4};
                    end
                    8'h0d: begin mem[tar[14:2]]<=current_data;if(csw[5:4]==1) tar<={tar[31:10],tar[9:0]+10'd4};end
                    8'h0e: rdata<=posted;
                    default: $fatal(1,"bad request %x",current_req);
                    endcase
                end
            end
        end
    end
endmodule
