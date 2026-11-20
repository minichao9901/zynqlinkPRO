`timescale 1ns/1ps
// Arm TPIU Manchester SWO: idle low, start high/low, then 1..8 bytes
// LSB first. A falling center represents one; a rising center represents zero.
// Two transitions can arrive per quartet at 100 Mbit/s. The previous edge
// anchors each interval so frequency drift never accumulates across a packet.
module selectio_manchester_rx(
    input wire clk, reset, enable, input wire [3:0] samples,
    input wire [15:0] min_short, short_limit, long_limit,
    output reg valid, output reg [7:0] data, output reg framing_error
);
    localparam IDLE=0, START=1, CENTER=2, BOUNDARY=3;
    reg previous;
    reg [15:0] age;
    wire [3:0] changes=samples^{samples[2:0],previous};
    wire [1:0] first=changes[0]?0:changes[1]?1:changes[2]?2:3;
    wire [1:0] last=changes[3]?3:changes[2]?2:changes[1]?1:0;
    wire [3:0] middle=changes & ~(4'b1<<first) & ~(4'b1<<last);
    wire [16:0] elapsed={1'b0,age}+first;
    wire [2:0] spacing={1'b0,last}-{1'b0,first};
    reg [1:0] present,short_pulse,long_pulse,level;
    reg glitch,timed_out;
    reg [1:0] state,next_state;
    reg [6:0] count,next_count;
    reg [7:0] shift,next_shift,byte_value;
    reg emit,error,capture;

    always @(posedge clk) begin
        previous<=samples[3];
        if(reset || !enable) begin
            age<=16'hffff;present<=0;glitch<=0;timed_out<=0;
        end else begin
            if (|changes) age<=16'd4-{14'b0,last};
            else if (age<16'hfffb) age<=age+4;
            else age<=16'hffff;
            present<={changes!=0 && first!=last,|changes};
            level<={samples[last],samples[first]};
            short_pulse<={(spacing>=min_short && spacing<short_limit),
                          (elapsed>=min_short && elapsed<short_limit)};
            long_pulse<={(spacing>=short_limit && spacing<=long_limit),
                         (elapsed>=short_limit && elapsed<=long_limit)};
            glitch<=|middle;
            timed_out<=changes==0 && age>long_limit;
        end
    end

    always @* begin
        next_state=state;next_count=count;next_shift=shift;
        emit=0;error=0;byte_value=0;capture=0;
        for(integer e=0;e<2;e=e+1) begin
            capture=0;
            if(present[e]) case(next_state)
                IDLE: if(level[e]) begin next_state=START;next_count=0; end
                START: begin
                    if (!level[e] && short_pulse[e]) next_state=CENTER;
                    else begin error=1;next_state=level[e] ? START : IDLE;next_count=0; end
                end
                CENTER,BOUNDARY: begin
                    if(next_state==CENTER && short_pulse[e]) next_state=BOUNDARY;
                    else if((next_state==CENTER && long_pulse[e]) ||
                            (next_state==BOUNDARY && short_pulse[e])) begin
                        capture=1;next_state=CENTER;
                    end else begin
                        // The low stop interval can end directly at the start
                        // of another frame. Only whole bytes form a legal tail.
                        error=next_count==0 || next_count[2:0]!=0 || !level[e];
                        next_state=level[e] ? START : IDLE;next_count=0;
                    end
                end
            endcase
            if(capture) begin
                if(next_count==64) begin error=1;next_state=IDLE;end
                else begin
                    next_shift={!level[e],next_shift[7:1]};
                    next_count=next_count+1'b1;
                    if(next_count[2:0]==0) begin emit=1;byte_value=next_shift;end
                end
            end
        end
        if(timed_out && (state==CENTER || state==BOUNDARY)) begin
            error=count==0 || count[2:0]!=0 || previous;
            next_state=IDLE;next_count=0;
        end
        if(glitch) begin next_state=IDLE;next_count=0;emit=0;error=1;end
    end
    always @(posedge clk) begin
        valid<=0;framing_error<=0;
        if(reset || !enable) begin state<=IDLE;count<=0;shift<=0;end
        else begin
            state<=next_state;count<=next_count;shift<=next_shift;
            valid<=emit;data<=byte_value;framing_error<=error;
        end
    end
endmodule
