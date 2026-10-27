`timescale 1ns/1ps
// RTT UP-channel reader. A packet is immutable from ready through DMA commit.
// RdOff is written only after the consumer acknowledges successful DDR DMA.
module probe_rtt_engine # (parameter TIMEOUT=262143, RETRIES=64) (
    input wire clk,rst_n, enable, available, buffer_free, commit,
    input wire [31:0] up_addr, ring_addr, ring_size, initial_rd,
    input wire [11:0] chunk,
    output wire active, output reg ready, output reg fault,
    output reg [11:0] length,
    output reg [31:0] drained,polls,errors,
    output reg byte_we, output reg [10:0] byte_addr, output reg [7:0] byte_data,
    output reg core_start, output reg [7:0] core_req,
    output reg [31:0] core_wdata,
    output wire core_next_valid, output wire [7:0] core_next_req,
    input wire core_busy,core_result_valid,core_next_ready,
    input wire [2:0] core_ack, input wire core_parity_err,
    input wire [31:0] core_rdata
);
    localparam IDLE=0, ISSUE=1, RESULT=2, SEGMENT=3, DMA=4, COMMITTED=5,CALCULATE=7;
    localparam SELECT=0,CSW=1,TAR=2,PRIME=3,DRW=4,LAST=5,WR_TAR=6,WR_RD=7;
    reg [2:0] state,phase;
    reg initialized, was_enabled, payload, committing;
    reg [31:0] rd, new_rd, address, available_count;
    reg [$clog2(TIMEOUT+1)-1:0] watchdog;
    reg [31:0] desc[0:3];
    reg [11:0] remaining;
    reg [10:0] offset;
    reg [8:0] words, index;
    reg [2:0] desc_base;
    reg [7:0] retry;
    reg [31:0] stage;
    reg [2:0] bytes_left,byte_index;
    reg [1:0] leading;
    reg [7:0] idle_delay;
    wire [31:0] available_bytes = desc[2]>=desc[3] ? desc[2]-desc[3] : ring_size-desc[3];
    wire [11:0] capped = available_count > chunk ? chunk : available_count[11:0];
    wire [31:0] desc_start=up_addr+4;
    wire [10:0] desc_room=1024-desc_start[9:0];
    // At most 2048 bytes, and never issue a posted read across AP TAR wrap.
    wire [31:0] segment_bytes = remaining > (1024-address[9:0]) ? (1024-address[9:0]) : remaining;
    assign active = (state!=IDLE && state!=DMA) || (enable && !fault);
    assign core_next_valid = state==RESULT && !core_parity_err && core_ack==1 &&
                             (phase==PRIME || phase==DRW);
    assign core_next_req = (phase==PRIME && words==1) || (phase==DRW && index+1==words-1) ? 8'h0e : 8'h0f;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            state<=IDLE;phase<=SELECT;ready<=0;fault<=0;length<=0;
            drained<=0;polls<=0;errors<=0;initialized<=0;was_enabled<=0;
            rd<=0;new_rd<=0;address<=0;watchdog<=0;available_count<=0;remaining<=0;offset<=0;
            words<=0;index<=0;desc_base<=0;retry<=RETRIES;payload<=0;committing<=0;stage<=0;
            bytes_left<=0;byte_index<=0;leading<=0;idle_delay<=0;
            byte_we<=0;byte_addr<=0;byte_data<=0;core_start<=0;core_req<=0;core_wdata<=0;
        end else begin
            core_start<=0;byte_we<=0;was_enabled<=enable;
            if(enable && !was_enabled && state==IDLE && !initialized) begin
                rd<=initial_rd;initialized<=0;fault<=0;drained<=0;polls<=0;errors<=0;
            end
            if(bytes_left!=0) begin
                byte_we<=1;byte_addr<=offset;byte_data<=stage[byte_index*8+:8];
                offset<=offset+1'b1;remaining<=remaining-1'b1;
                bytes_left<=bytes_left-1'b1;byte_index<=byte_index+1'b1;
            end
            case(state)
            IDLE: if(enable && was_enabled && !fault && buffer_free && available) begin
                if(idle_delay!=0) idle_delay<=idle_delay-1'b1;
                else begin
                    address<=desc_start;words<=desc_room<16 ? desc_room>>2 : 4;
                    desc_base<=0;index<=0;payload<=0;
                    retry<=RETRIES;committing<=0;phase<=initialized ? TAR : SELECT;state<=ISSUE;
                end
            end
            ISSUE: if(!core_busy && available) begin
                case(phase)
                SELECT: begin core_req<=8'h08;core_wdata<=0;end
                CSW: begin core_req<=8'h01;core_wdata<=32'h23000012;end
                TAR: begin core_req<=8'h05;core_wdata<={address[31:2],2'b00};end
                PRIME,DRW: begin core_req<=8'h0f;core_wdata<=0;end
                LAST: begin core_req<=8'h0e;core_wdata<=0;end
                WR_TAR: begin core_req<=8'h05;core_wdata<=up_addr+16;end
                WR_RD: begin core_req<=8'h0d;core_wdata<=new_rd;end
                endcase
                core_start<=1;watchdog<=TIMEOUT;state<=RESULT;
            end
            RESULT: if(core_result_valid) begin
                if(core_ack==2 && !core_parity_err && retry!=0) begin retry<=retry-1'b1;state<=ISSUE;end
                else if(core_ack!=1 || core_parity_err) begin
                    fault<=1;errors<=errors+1'b1;
                    // A failed RdOff write is idempotent: keep the DMA-owned
                    // packet and retry the same write when commit is repeated.
                    state<=ready ? DMA : IDLE;
                end else begin
                    watchdog<=TIMEOUT;retry<=RETRIES;
                    case(phase)
                    SELECT: begin phase<=CSW;state<=ISSUE;end
                    CSW: begin initialized<=1;phase<=committing ? WR_TAR : TAR;state<=ISSUE;end
                    TAR: begin phase<=PRIME;state<=ISSUE;end
                    PRIME: begin
                        phase<=words==1 ? LAST : DRW;
                        state<=core_next_ready ? RESULT : ISSUE;
                    end
                    DRW,LAST: begin
                        if(payload) begin
                            stage<=core_rdata;byte_index<=leading;leading<=0;
                            bytes_left<=remaining < (4-leading) ? remaining : (4-leading);
                        end else desc[desc_base+index]<=core_rdata;
                        index<=index+1'b1;
                        if(phase==LAST) state<=SEGMENT;
                        else begin
                            if(index+1==words-1) phase<=LAST;
                            state<=core_next_ready ? RESULT : ISSUE;
                        end
                    end
                    WR_TAR: begin phase<=WR_RD;state<=ISSUE;end
                    WR_RD: begin
                        // Drain the posted AP write before exposing completion.
                        phase<=LAST;payload<=0;state<=COMMITTED;
                    end
                    endcase
                end
            end else if(watchdog==0) begin fault<=1;errors<=errors+1'b1;state<=ready ? DMA : IDLE;end
            else watchdog<=watchdog-1'b1;
            SEGMENT: if(bytes_left==0 && !byte_we) begin
                if(!payload) begin
                    if(desc_base+words<4) begin
                        desc_base<=desc_base+words;words<=4-desc_base-words;
                        index<=0;phase<=TAR;state<=ISSUE;
                    end else begin
                    polls<=polls+1'b1;
                    if(desc[0]!=ring_addr || desc[1]!=ring_size || desc[2]>=ring_size || desc[3]!=rd) begin
                        fault<=1;errors<=errors+1'b1;state<=IDLE;
                    end else begin available_count<=available_bytes;state<=CALCULATE;end
                    end
                end else if(remaining==0) begin ready<=1;state<=DMA;end
                else begin
                    words<=(segment_bytes+address[1:0]+3)>>2;index<=0;
                    phase<=TAR;state<=ISSUE;
                    // address is the next unread target byte; advance at the
                    // next segment using the number of bytes actually stored.
                end
            end
            CALCULATE: if(capped==0 || !enable) begin idle_delay<=128;state<=IDLE;end
            else begin
                length<=capped;remaining<=capped;offset<=0;
                new_rd<=rd+capped==ring_size ? 0 : rd+capped;
                address<=ring_addr+rd;leading<=(ring_addr+rd)&3;
                payload<=1;state<=SEGMENT;
            end
            DMA: if(commit) begin fault<=0;committing<=1;phase<=SELECT;retry<=RETRIES;state<=ISSUE;end
            COMMITTED: if(!core_busy) begin
                // AP writes are posted: a DP RDBUFF read confirms the write
                // reached the target. This state starts that read once.
                core_req<=8'h0e;core_wdata<=0;core_start<=1;watchdog<=TIMEOUT;
                state<=6;
            end
            6: if(core_result_valid) begin
                if(core_ack==1 && !core_parity_err) begin
                    rd<=new_rd;drained<=drained+length;ready<=0;state<=IDLE;
                end else if(core_ack==2 && !core_parity_err && retry!=0) begin retry<=retry-1'b1;state<=COMMITTED;end
                else begin fault<=1;errors<=errors+1'b1;state<=DMA;end
            end else if(watchdog==0) begin fault<=1;errors<=errors+1'b1;state<=DMA;end
            else watchdog<=watchdog-1'b1;
            endcase
            // Update the segment address only after its final returned word.
            if(state==RESULT && core_result_valid && core_ack==1 && !core_parity_err &&
               phase==LAST) address<=address+((words*4)-address[1:0]);
        end
    end
endmodule
