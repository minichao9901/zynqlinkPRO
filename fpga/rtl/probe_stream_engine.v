`timescale 1ns/1ps
// Packet BRAM at 0x42020000. First 4 KiB are registers, followed by eight
// 2 KiB immutable packet banks. Port A is read by AXI CDMA; port B is PL-only.
// PS handles descriptors and USB ownership, never individual sample words.
module probe_stream_engine (
    input wire clk,rst_n,
    input wire host_en,input wire [3:0] host_we,input wire [31:0] host_addr,host_wdata,
    output wire [31:0] host_rdata,
    input wire sample_empty, input wire [31:0] sample_data,tick,
    input wire sampler_active, output wire sample_pop,
    output wire rtt_active, output wire core_start,output wire [7:0] core_req,
    output wire [31:0] core_wdata,output wire core_next_valid,
    output wire [7:0] core_next_req,
    input wire core_available,core_busy,core_result_valid,core_next_ready,
    input wire [2:0] core_ack,input wire core_parity_err,input wire [31:0] core_rdata
);
    reg [1:0] mode;
    reg hss_session;
    reg [31:0] head,tail,packet_seq,produced;
    reg [11:0] lengths[0:7];
    reg [31:0] config_words[0:15];
    reg [6:0] byte_map[0:63];
    reg [6:0] config_index;
    reg [31:0] up_addr,ring_addr,ring_size,initial_rd;
    reg [11:0] chunk;
    wire ctrl_write=host_en && (&host_we) && host_addr[14:2]==0;
    wire ack_write=host_en && (&host_we) && host_addr[14:2]==3 && host_wdata[0];
    wire reset_packets=ctrl_write && host_wdata[8] && !sampler_active && !rtt_active;
    wire full=head-tail==8;
    wire [31:0] queued=head-tail;
    wire [2:0] bank=head[2:0];
    wire [2:0] oldest=tail[2:0];
    wire rtt_ready,rtt_fault;
    wire [11:0] rtt_length;
    wire [31:0] rtt_drained,rtt_polls,rtt_errors;
    wire rtt_byte_we;
    wire [10:0] rtt_byte_addr;
    wire [7:0] rtt_byte_data;
    reg rtt_announced,rtt_commit;
    probe_rtt_engine u_rtt (
        .clk(clk),.rst_n(rst_n && !reset_packets),.enable(mode==2),
        .available(core_available),.buffer_free(!full),.commit(rtt_commit),
        .up_addr(up_addr),.ring_addr(ring_addr),.ring_size(ring_size),.initial_rd(initial_rd),.chunk(chunk),
        .active(rtt_active),.ready(rtt_ready),.fault(rtt_fault),.length(rtt_length),
        .drained(rtt_drained),.polls(rtt_polls),.errors(rtt_errors),
        .byte_we(rtt_byte_we),.byte_addr(rtt_byte_addr),.byte_data(rtt_byte_data),
        .core_start(core_start),.core_req(core_req),.core_wdata(core_wdata),
        .core_next_valid(core_next_valid),.core_next_req(core_next_req),
        .core_busy(core_busy),.core_result_valid(core_result_valid),.core_next_ready(core_next_ready),
        .core_ack(core_ack),.core_parity_err(core_parity_err),.core_rdata(core_rdata)
    );
    // Byte enables allow arbitrary subword/unaligned HSS layouts and RTT tails
    // without read-modify-write operations or PS gather/copy loops.
    wire [31:0] memory_data;
    reg [31:0] register_data;
    reg memory_selected;
    reg mem_we;
    reg [3:0] mem_mask;
    reg [11:0] mem_addr;
    reg [31:0] mem_data;
    wire [11:0] host_word=(host_addr[14:0]-15'd4096)>>2;
    assign host_rdata=memory_selected ? memory_data : register_data;
    xpm_memory_tdpram #(
        .ADDR_WIDTH_A(12),.ADDR_WIDTH_B(12),.AUTO_SLEEP_TIME(0),
        .BYTE_WRITE_WIDTH_A(8),.BYTE_WRITE_WIDTH_B(8),.CLOCKING_MODE("common_clock"),
        .MEMORY_INIT_FILE("none"),.MEMORY_INIT_PARAM("0"),.MEMORY_OPTIMIZATION("true"),
        .MEMORY_PRIMITIVE("block"),.MEMORY_SIZE(131072),.MESSAGE_CONTROL(0),
        .READ_DATA_WIDTH_A(32),.READ_DATA_WIDTH_B(32),.READ_LATENCY_A(1),.READ_LATENCY_B(1),
        .READ_RESET_VALUE_A("0"),.READ_RESET_VALUE_B("0"),.RST_MODE_A("SYNC"),.RST_MODE_B("SYNC"),
        .USE_MEM_INIT(0),.WAKEUP_TIME("disable_sleep"),.WRITE_DATA_WIDTH_A(32),.WRITE_DATA_WIDTH_B(32),
        .WRITE_MODE_A("read_first"),.WRITE_MODE_B("read_first")
    ) u_packet_bram (
        .clka(clk),.ena(host_en && host_addr[14:12]!=0),.wea(4'd0),.addra(host_word),.dina(32'd0),
        .douta(memory_data),.rsta(1'b0),.regcea(1'b1),
        .clkb(clk),.enb(mem_we),.web(mem_mask),.addrb(mem_addr),.dinb(mem_data),.doutb(),.rstb(1'b0),.regceb(1'b1)
    );
    always @(posedge clk) begin
        if(host_en) memory_selected<=host_addr[14:12]!=0;
        if(host_en && host_addr[14:12]==0) case(host_addr[11:2])
        0: register_data<=32'h53545232;
        1: register_data<={queued[15:0],8'd0,rtt_fault,3'd0,rtt_active,sampler_active,mode};
        2: register_data<= head!=tail ? {7'd0,rtt_announced,5'd0,oldest,4'd0,lengths[oldest]} : 0;
        3: register_data<=tail;
        4: register_data<=produced;
        5: register_data<=packet_seq;
        6: register_data<={25'd0,config_index};
        7: register_data<=config_index<16 ? config_words[config_index] : {25'd0,byte_map[config_index-16]};
        8: register_data<=up_addr;
        9: register_data<=ring_addr;
        10: register_data<=ring_size;
        11: register_data<=initial_rd;
        12: register_data<=chunk;
        13: register_data<=rtt_polls;
        14: register_data<=rtt_drained;
        15: register_data<=rtt_errors;
        default: register_data<=0;
        endcase
    end
    localparam EMPTY=0,CLEAR=1,STAMP=2,WORDS=3,GATHER=4,HEADER=5,PUBLISH=6,CHECK=7;
    reg [2:0] state;
    reg [6:0] cursor;
    reg [4:0] word_index;
    reg [31:0] values[0:23];
    reg [31:0] stamp,first_stamp,last_stamp,packet_started,sample_delta;
    reg [63:0] elapsed_ticks,convert_input;
    reg [31:0] convert_quotient;
    reg [6:0] convert_bits;
    reg [4:0] convert_remainder;
    wire [5:0] div_step={convert_remainder,convert_input[63]};
    reg have_origin;
    reg [8:0] position;
    reg [8:0] samples;
    reg [1:0] header_index;
    wire [6:0] frame_size=config_words[0][6:0];
    wire v2=config_words[1]==2;
    wire [31:0] period=config_words[2];
    wire [4:0] word_count=config_words[5][4:0];
    wire [8:0] payload_bytes=samples*frame_size;
    wire gap=samples!=0 && stamp-last_stamp!=period;
    assign sample_pop=(state==CHECK && !gap) || state==WORDS;
    always @(posedge clk or negedge rst_n) begin
        if(!rst_n) begin
            mode<=0;hss_session<=0;head<=0;tail<=0;packet_seq<=1;produced<=0;config_index<=0;
            up_addr<=0;ring_addr<=0;ring_size<=0;initial_rd<=0;chunk<=2048;
            rtt_announced<=0;rtt_commit<=0;state<=EMPTY;cursor<=0;word_index<=0;
            stamp<=0;first_stamp<=0;last_stamp<=0;have_origin<=0;packet_started<=0;
            sample_delta<=0;elapsed_ticks<=0;convert_input<=0;convert_quotient<=0;
            convert_bits<=0;convert_remainder<=0;
            position<=16;samples<=0;header_index<=0;mem_we<=0;mem_mask<=0;mem_addr<=0;mem_data<=0;
        end else begin
            mem_we<=0;rtt_commit<=0;
            // Serial /24 conversion is only needed at a v1 packet boundary.
            // Keep the FIFO read, timestamp subtraction, accumulation and
            // division on separate register stages; v2 never waits for it.
            if(convert_bits!=0) begin
                convert_input<={convert_input[62:0],1'b0};
                convert_quotient<={convert_quotient[30:0],div_step>=24};
                convert_remainder<=div_step>=24 ? div_step-24 : div_step;
                convert_bits<=convert_bits-1'b1;
                if(convert_bits==1) first_stamp<={convert_quotient[30:0],div_step>=24};
            end
            if(host_en && &host_we && host_addr[14:12]==0) case(host_addr[11:2])
            0: if(host_wdata[1:0]!=3) begin mode<=host_wdata[1:0];if(host_wdata[1:0]==1) hss_session<=1;end
            6: config_index<=host_wdata[6:0];
            7: if(mode==0) begin
                if(config_index<16) config_words[config_index]<=host_wdata;
                else if(config_index<80) byte_map[config_index-16]<=host_wdata[6:0];
                if(config_index==3) packet_seq<=host_wdata;
            end
            8: if(mode==0) up_addr<=host_wdata;
            9: if(mode==0) ring_addr<=host_wdata;
            10: if(mode==0) ring_size<=host_wdata;
            11: if(mode==0) initial_rd<=host_wdata;
            12: if(mode==0) chunk<=host_wdata>2048 || host_wdata==0 ? 2048 : host_wdata[11:0];
            endcase
            if(ack_write && head!=tail) begin
                if(mode==2 || rtt_announced) rtt_commit<=1;
                else tail<=tail+1'b1;
            end
            if(rtt_byte_we) begin
                mem_we<=1;mem_addr<={bank,rtt_byte_addr[10:2]};
                mem_mask<=4'b1<<rtt_byte_addr[1:0];mem_data<={4{rtt_byte_data}};
            end
            if(rtt_ready && !rtt_announced) begin
                lengths[bank]<=rtt_length;head<=head+1'b1;rtt_announced<=1;
            end
            if(rtt_announced && !rtt_ready) begin tail<=tail+1'b1;rtt_announced<=0;end
            case(state)
            EMPTY: if(hss_session && !full && !sample_empty) begin cursor<=0;state<=CLEAR;end
            CLEAR: begin
                mem_we<=1;mem_mask<=15;mem_addr<={bank,2'b00,cursor};mem_data<=0;
                if(cursor==127) begin position<=16;samples<=0;state<=STAMP;packet_started<=tick;end
                else cursor<=cursor+1'b1;
            end
            STAMP: if(!sample_empty) begin
                stamp<=sample_data;state<=CHECK;
            end else if(samples!=0 && ((!sampler_active && mode==0) || tick-packet_started>=240000)) begin
                header_index<=0;state<=HEADER;
            end else if(mode==0 && !sampler_active && samples==0) state<=EMPTY;
            CHECK: begin
                if(gap) begin header_index<=0;state<=HEADER;end
                else begin
                    if(samples==0 && v2) first_stamp<=stamp;
                    word_index<=0;state<=WORDS;
                end
            end
            WORDS: begin
                values[word_index]<=sample_data;
                if(word_index==0) begin
                    sample_delta<=have_origin ? stamp-last_stamp : 0;
                    last_stamp<=stamp;have_origin<=1;
                end
                if(word_index+1==word_count) begin cursor<=0;state<=GATHER;end
                else word_index<=word_index+1'b1;
            end
            GATHER: begin
                if(cursor==0 && !v2) begin
                    elapsed_ticks<=elapsed_ticks+sample_delta;
                    if(samples==0) begin
                        convert_input<=elapsed_ticks+sample_delta;convert_bits<=64;
                        convert_remainder<=0;convert_quotient<=0;
                    end
                end
                mem_we<=1;mem_addr<={bank,2'b00,position[8:2]};mem_mask<=4'b1<<position[1:0];
                mem_data<={4{values[byte_map[cursor][6:2]][byte_map[cursor][1:0]*8+:8]}};
                position<=position+1'b1;
                if(cursor+1==frame_size) begin
                    samples<=samples+1'b1;produced<=produced+1'b1;
                    if(position+1+frame_size>512) begin header_index<=0;state<=HEADER;end
                    else state<=STAMP;
                end else cursor<=cursor+1'b1;
            end
            HEADER: if(convert_bits==0) begin
                mem_we<=1;mem_mask<=15;mem_addr<={bank,7'd0,header_index};
                case(header_index)
                0: mem_data<={8'd2,config_words[1][7:0],16'h4a53};
                1: mem_data<=packet_seq;
                2: mem_data<=first_stamp;
                3: mem_data<={7'd0,payload_bytes,7'd0,samples};
                endcase
                if(header_index==3) state<=PUBLISH;
                else header_index<=header_index+1'b1;
            end
            PUBLISH: begin
                lengths[bank]<=512;head<=head+1'b1;packet_seq<=packet_seq+1'b1;state<=EMPTY;
            end
            endcase
            if(reset_packets) begin
                mode<=0;head<=0;tail<=0;packet_seq<=1;produced<=0;
                state<=EMPTY;have_origin<=0;rtt_announced<=0;samples<=0;hss_session<=0;
                elapsed_ticks<=0;convert_bits<=0;
            end
        end
    end
endmodule
