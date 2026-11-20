`timescale 1ns/1ps
// GP1 peripheral for SPI, UART and SWO. TX uses synchronous dual-port RAM.
// The producer owns each RX byte until software acknowledges its USB delivery.
module selectio_aux_regs(
    (* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET axi_aresetn" *)
    input wire axi_aclk, axi_aresetn,
    input wire [16:0] s_axi_awaddr, input wire [2:0] s_axi_awprot,
    input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output reg [1:0] s_axi_bresp,output reg s_axi_bvalid,input wire s_axi_bready,
    input wire [16:0] s_axi_araddr,input wire [2:0] s_axi_arprot,
    input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg [1:0] s_axi_rresp,
    output reg s_axi_rvalid,input wire s_axi_rready,
    input wire quad_clk, phy_reset, pad_granted, uart_granted,
    input wire [3:0] pad_samples,output wire pad_request, uart_request, spi_selected, monitor_tdi,
    output wire [3:0] clock_slots, select_slots, tx_slots
);
    // flags[1:0] receive codec: 0 off, 1 UART 8N1, 2 Manchester SWO.
    // flags[2] owns the SPI pins, flags[3] owns UART TX on TDI.
    reg [3:0] flags;
    reg [31:0] period_q8;
    reg [15:0] min_short,short_limit,long_limit;
    reg [7:0] spi_config;
    reg [1:0] test_config;
    (* ASYNC_REG="TRUE" *) reg [1:0] test_meta,test_io;
    always @(posedge quad_clk) begin
        if(phy_reset) begin test_meta<=0;test_io<=0;end
        else begin test_meta<=test_config;test_io<=test_meta;end
    end
    assign monitor_tdi=test_io[0];
    assign pad_request=flags[2] || (test_config[1] && flags[3]);
    (* ASYNC_REG="TRUE" *) reg [3:0] flags_meta,flags_io;
    (* ASYNC_REG="TRUE" *) reg [1:0] grant_sync;
    wire uart_bypass=test_io[1] && flags_io[3];
    assign uart_request=flags_io[3] && !uart_bypass;
    wire granted=(flags_io[2] || uart_bypass) ? pad_granted : uart_granted;
    always @(posedge quad_clk) begin
        if(phy_reset) begin flags_meta<=0;flags_io<=0;end
        else begin flags_meta<=flags;flags_io<=flags_meta;end
    end
    assign spi_selected=flags_io[2] || uart_bypass;

    wire [7:0] uart_byte,manchester_byte,spi_byte;
    wire uart_valid,manchester_valid,spi_valid,uart_error,manchester_error;
    reg fast_rate;
    reg [31:0] rx_period;
    reg [15:0] rx_min_short,rx_short_limit,rx_long_limit;
    reg rx_phase;
    always @(posedge quad_clk) begin
        if(!flags_io[1:0]) begin
            fast_rate<=period_q8>=1023 && period_q8<=1025;
            rx_period<=period_q8;
            rx_min_short<=min_short;rx_short_limit<=short_limit;rx_long_limit<=long_limit;
            rx_phase<=spi_config[2];
        end
    end
    selectio_uart_rx uart_rx(quad_clk,phy_reset,flags_io[1:0]==1,pad_samples,rx_period,
                             uart_valid,uart_byte,uart_error);

    wire regular_valid,regular_error,fast_valid,fast_error;
    wire [7:0] regular_byte,fast_byte;
    assign manchester_valid=regular_valid || fast_valid;
    assign manchester_error=regular_error || fast_error;
    assign manchester_byte=fast_rate ? fast_byte : regular_byte;
    selectio_manchester_fast fast_decoder(quad_clk,phy_reset,flags_io[1:0]==2 && fast_rate,
        rx_phase,pad_samples,fast_valid,fast_byte,fast_error);
    selectio_manchester_rx manchester_rx(quad_clk,phy_reset,flags_io[1:0]==2 && !fast_rate,pad_samples,
                       rx_min_short,rx_short_limit,rx_long_limit,regular_valid,regular_byte,regular_error);
    reg launch;
    reg [12:0] tx_length;
    wire launch_io,tx_busy,tx_done,done_spi,done_uart;
    wire [12:0] active_length;
    wire [9:0] spi_addr,uart_addr;
    wire [3:0] mosi,uart_out;
    wire [31:0] active_period;
    wire [7:0] active_spi_config;
    wire send_spi;
    selectio_command_bridge #(.REQUEST_BITS(54),.RESPONSE_BITS(1)) launch_bridge(
        .host_clk(axi_aclk),.io_clk(quad_clk),.reset(!axi_aresetn || phy_reset),
        .host_start(launch),.host_request({flags[2],spi_config,period_q8,tx_length}),
        .host_busy(tx_busy),.host_done(tx_done),.host_response(),
        .granted(granted),.io_start(launch_io),.io_request({send_spi,active_spi_config,active_period,active_length}),
        .io_done(done_spi || done_uart),.io_response(1'b1));
    reg [31:0] tx_q;
    wire [9:0] tx_address=flags_io[2] ? spi_addr : uart_addr;
    wire [3:0] spi_sck,spi_cs;
    selectio_spi spi(quad_clk,phy_reset,launch_io && send_spi,active_spi_config[1:0],
                     active_length,active_spi_config[7:2],spi_addr,tx_q,pad_samples,
                     spi_sck,spi_cs,mosi,spi_valid,,spi_byte,,done_spi);
    wire uart_busy;
    selectio_uart_tx uart_tx(quad_clk,phy_reset,launch_io && !send_spi,
                             active_length,active_period,tx_q,uart_addr,uart_out,uart_busy,done_uart);
    assign clock_slots=uart_bypass ? (uart_busy ? 4'b1100 : 4'b0) : spi_sck;
    assign select_slots=uart_bypass ? 4'b0 : spi_cs;
    assign tx_slots=flags_io[2] ? mosi : uart_out;
    reg [16:0] aw;
    reg [31:0] wd;
    reg [3:0] strobe;
    reg have_aw,have_w,ram_pending,completed;
    wire write_beat=have_aw && have_w && !s_axi_bvalid;
    wire aligned=aw[1:0]==0 && strobe==4'hf;
    wire tx_write=write_beat && aligned && aw[16:12]==1 && !tx_busy && !launch;
    (* ram_style="block" *) reg [31:0] tx_ram[0:1023];
    always @(posedge axi_aclk) if(tx_write) tx_ram[aw[11:2]]<=wd;
    always @(posedge quad_clk) tx_q<=tx_ram[tx_address];

    // Acknowledgement values can jump by many bytes. Transfer them as
    // a stable mailbox, never a multi-bit Gray transition.
    reg update_reader,clear_request;
    reg [16:0] reader_value,reader_view;
    wire ack_busy,ack_done,apply_reader,clear_io;
    wire [16:0] new_reader;
    reg applied;
    always @(posedge quad_clk) applied<=apply_reader;
    selectio_command_bridge #(.REQUEST_BITS(18),.RESPONSE_BITS(1)) reader_bridge(
        .host_clk(axi_aclk),.io_clk(quad_clk),.reset(!axi_aresetn || phy_reset),
        .host_start(update_reader),.host_request({clear_request,reader_value}),
        .host_busy(ack_busy),.host_done(ack_done),.host_response(),
        .granted(1'b1),.io_start(apply_reader),.io_request({clear_io,new_reader}),
        .io_done(applied),.io_response(1'b1));
    reg [16:0] writer,reader,writer_gray;
    reg [31:0] drops,errors;
    wire full=writer=={~reader[16],reader[15:0]};
    // SPI results take the ring only in SPI mode with the optional serial
    // monitor disabled. A serial monitor can observe MISO during a test.
    wire spi_capture=flags_io[2] && flags_io[1:0]==0;
    reg produced;
    reg [7:0] produced_byte;
    always @(posedge quad_clk) begin
        produced<=!phy_reset && (spi_capture ? spi_valid : uart_valid || manchester_valid);
        produced_byte<=spi_capture ? spi_byte : flags_io[1:0]==1 ? uart_byte : manchester_byte;
    end
    wire accepted=produced && !full;
    wire [16:0] next_writer=writer+1'b1;
    always @(posedge quad_clk) begin
        if(phy_reset || (apply_reader && clear_io)) begin
            writer<=0;reader<=0;writer_gray<=0;drops<=0;errors<=0;
        end else begin
            if(apply_reader) reader<=new_reader;
            if(accepted) begin writer<=next_writer;writer_gray<=next_writer^(next_writer>>1);end
            if(produced && full && !(&drops)) drops<=drops+1'b1;
            if((uart_error || manchester_error) && !(&errors)) errors<=errors+1'b1;
        end
    end
    (* ASYNC_REG="TRUE" *) reg [16:0] wr_meta,wr_gray_sync;
    reg [16:0] writer_view;
    function [16:0] from_gray(input [16:0] g);
        integer i;
        begin from_gray[16]=g[16];for(i=15;i>=0;i=i-1) from_gray[i]=from_gray[i+1]^g[i];end
    endfunction
    wire [16:0] available=writer_view-reader_view;
    wire ram_read=s_axi_arvalid && s_axi_arready && s_axi_araddr[16] && s_axi_araddr[1:0]==0;
    wire [31:0] ram_q;
    for(genvar lane=0;lane<4;lane=lane+1) begin:receive_ram
        (* ram_style="block" *) reg [7:0] bytes[0:16383];
        reg [7:0] q;
        always @(posedge quad_clk)
            if(accepted && writer[1:0]==lane) bytes[writer[15:2]]<=produced_byte;
        always @(posedge axi_aclk) if(ram_read) q<=bytes[s_axi_araddr[15:2]];
        assign ram_q[8*lane+:8]=q;
    end
    // Capture the two 32-bit counters under an explicit request, including
    // while receiving. All bits cross with their completion handshake.
    reg snapshot_request;
    wire snapshot_busy,snapshot_done,snapshot_io;
    wire [63:0] snapshot;
    selectio_command_bridge #(.REQUEST_BITS(1),.RESPONSE_BITS(64)) counters(
        .host_clk(axi_aclk),.io_clk(quad_clk),.reset(!axi_aresetn || phy_reset),
        .host_start(snapshot_request),.host_request(1'b0),.host_busy(snapshot_busy),
        .host_done(snapshot_done),.host_response(snapshot),.granted(1'b1),
        .io_start(snapshot_io),.io_request(),.io_done(snapshot_io),.io_response({errors,drops}));
    assign s_axi_awready=!have_aw && !s_axi_bvalid;
    assign s_axi_wready=!have_w && !s_axi_bvalid;
    assign s_axi_arready=!s_axi_rvalid && !ram_pending;
    always @(posedge axi_aclk) begin
        wr_meta<=writer_gray;wr_gray_sync<=wr_meta;writer_view<=from_gray(wr_gray_sync);
        grant_sync<={grant_sync[0],granted};
        launch<=0;update_reader<=0;snapshot_request<=0;
        if(!axi_aresetn) begin
            flags<=0;period_q8<=888889;spi_config<=0;test_config<=0;
            min_short<=1;short_limit<=3;long_limit<=5;
            have_aw<=0;have_w<=0;s_axi_bvalid<=0;s_axi_rvalid<=0;ram_pending<=0;
            reader_view<=0;completed<=0;grant_sync<=0;
        end else begin
            if(tx_done) completed<=1;
            if(ack_done) reader_view<=clear_request ? 0 : reader_value;
            if(s_axi_awvalid && s_axi_awready) begin aw<=s_axi_awaddr;have_aw<=1;end
            if(s_axi_wvalid && s_axi_wready) begin wd<=s_axi_wdata;strobe<=s_axi_wstrb;have_w<=1;end
            if(s_axi_bready) s_axi_bvalid<=0;
            if(write_beat) begin
                have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=0;
                if(!aligned) s_axi_bresp<=2;
                else if(!tx_write) case(aw)
                    'h08: if(!tx_busy && !launch && wd<16 && wd[1:0]!=3 && wd[3:2]!=3) flags<=wd[3:0];else s_axi_bresp<=2;
                    'h0c: if(!flags && wd>=1024) period_q8<=wd;else s_axi_bresp<=2;
                    'h10: if(!flags) begin min_short<=wd[15:0];short_limit<=wd[31:16];end else s_axi_bresp<=2;
                    'h14: if(!flags) long_limit<=wd[15:0];else s_axi_bresp<=2;
                    'h30: if(!flags && wd<4) test_config<=wd[1:0];else s_axi_bresp<=2;
                    'h18: if(!tx_busy && !launch && wd<256) spi_config<=wd[7:0];else s_axi_bresp<=2;
                    'h1c: if(grant_sync[1] && !tx_busy && !launch && wd!=0 && wd<=4096) begin
                        tx_length<=wd[12:0];launch<=1;completed<=0;
                    end else s_axi_bresp<=2;
                    'h20: if(!ack_busy && !update_reader && !ack_done && wd!=0 && wd<=available) begin
                        reader_value<=reader_view+wd[16:0];clear_request<=0;update_reader<=1;
                    end else s_axi_bresp<=2;
                    'h24: if(!flags && !ack_busy && !update_reader && !ack_done) begin
                        clear_request<=1;reader_value<=0;update_reader<=1;
                    end else s_axi_bresp<=2;
                    'h28: if(!snapshot_busy && !snapshot_request) snapshot_request<=1;else s_axi_bresp<=2;
                    default:s_axi_bresp<=2;
                endcase
            end
            if(s_axi_rready) s_axi_rvalid<=0;
            if(ram_pending) begin ram_pending<=0;s_axi_rdata<=ram_q;s_axi_rresp<=0;s_axi_rvalid<=1;end
            if(s_axi_arvalid && s_axi_arready) begin
                if(ram_read) ram_pending<=1;
                else begin
                    s_axi_rvalid<=1;s_axi_rresp<=0;
                    case(s_axi_araddr)
                        'h00:s_axi_rdata<=32'h41555831;
                        'h04:s_axi_rdata<={27'b0,snapshot_busy||snapshot_request,ack_busy||update_reader||ack_done,completed,tx_busy||launch,grant_sync[1]};
                        'h08:s_axi_rdata<={28'd0,flags};
                        'h0c:s_axi_rdata<=period_q8;
                        'h20:s_axi_rdata<={15'd0,reader_view};
                        'h24:s_axi_rdata<={15'd0,available};
                        'h28:s_axi_rdata<=snapshot[31:0];
                        'h2c:s_axi_rdata<=snapshot[63:32];
                        default: begin s_axi_rdata<=0;s_axi_rresp<=2;end
                    endcase
                end
            end
        end
    end
endmodule
