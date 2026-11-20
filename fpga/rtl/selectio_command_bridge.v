`timescale 1ns/1ps
// Single outstanding descriptor. Source payload is immutable from request
// toggle until response. The response is registered before its toggle crosses.
module selectio_command_bridge #(parameter REQUEST_BITS=40, RESPONSE_BITS=36)(
    input wire host_clk, io_clk, reset,
    input wire host_start, input wire [REQUEST_BITS-1:0] host_request,
    output reg host_busy, host_done, output reg [RESPONSE_BITS-1:0] host_response,
    input wire granted, output reg io_start, output reg [REQUEST_BITS-1:0] io_request,
    input wire io_done, input wire [RESPONSE_BITS-1:0] io_response
);
    reg request_tag, response_tag, active;
    reg [REQUEST_BITS-1:0] held_request;
    reg [RESPONSE_BITS-1:0] held_response;
    (* ASYNC_REG="TRUE" *) reg [1:0] response_sync, request_sync;
    // Asynchronous assertion and synchronous release in each domain.
    (* ASYNC_REG="TRUE" *) reg [2:0] hr=7, ir=7;
    always @(posedge host_clk or posedge reset)
        if(reset) hr<=7;else hr<={hr[1:0],1'b0};
    always @(posedge io_clk or posedge reset)
        if(reset) ir<=7;else ir<={ir[1:0],1'b0};
    always @(posedge host_clk) begin
        host_done<=0;
        if(hr[2]) begin host_busy<=0;host_response<=0;request_tag<=0;response_sync<=0;end
        else begin
            response_sync<={response_sync[0],response_tag};
            if(host_start && !host_busy) begin
                held_request<=host_request;
                request_tag<=!request_tag;
                host_busy<=1;
            end else if(host_busy && response_sync[1]==request_tag) begin
                host_response<=held_response;
                host_done<=1;
                host_busy<=0;
            end
        end
    end
    always @(posedge io_clk) begin
        io_start<=0;
        if(ir[2]) begin active<=0;response_tag<=0;request_sync<=0;end
        else begin
            request_sync<={request_sync[0],request_tag};
            if (!active && granted && request_sync[1]!=response_tag) begin
                io_request<=held_request;
                io_start<=1;
                active<=1;
            end else if(active && io_done) begin
                held_response<=io_response;
                response_tag<=request_sync[1];
                active<=0;
            end
        end
    end
endmodule
