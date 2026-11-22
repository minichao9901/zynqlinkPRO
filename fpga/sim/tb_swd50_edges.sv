`timescale 1ns/1ps
module tb_swd50_edges #(parameter VARIABLE_CLOCK=0);
    bit ref_clk=0, resetn=0, released=0, start=0;
    realtime ref_ns=5.0, nominal_period=20.0;
    reg [1:0] rate=0;
    always #(ref_ns/2) ref_clk = ~ref_clk;
    wire serial_rx_clk, serial_clk, quad_clk, octet_clk, phy_reset, swd_reset;
    wire [2:0] owner;
    wire [3:0] clocks_out, data_out, release_out, rx;
    wire [3:0] batch_clk, batch_data, batch_release;
    bit batch_mode=0, run_batch=0;
    wire batch_done, batch_failed, batch_write;
    wire [9:0] command_addr, retired;
    wire [3:0] batch_error;
    wire [15:0] retries;
    wire [31:0] batch_result;
    wire [8:0] result_index;
    reg [31:0] command_word;
    wire clk_pin, tdi_pin;
    tri1 data_pin;
    wire done, parity_error;
    wire [2:0] ack;
    wire [31:0] read_data;
    reg [7:0] header;
    integer sample_slot=22, idle=0;
    realtime return_ns=16;
    localparam [31:0] HOST_DATA=32'h6329f682;
    localparam [31:0] TARGET_DATA=32'hdcf416a5;
    localparam [2:0] OK=1, WAIT_ACK=2, FAULT_ACK=4;

    always @(posedge quad_clk)
        command_word <= command_addr[0] ? HOST_DATA : command_addr[9:1]==0 ? 32'd15 : 32'd13;

    selectio_clocking #(.VARIABLE_CLOCK(VARIABLE_CLOCK)) clocks(ref_clk,resetn,1'b1,1'b1,1'b0,released,1'b0,1'b0,1'b0,
        serial_clk,quad_clk,octet_clk,phy_reset,,swd_reset,,owner,,serial_rx_clk,2'b0,1'b0,);
    selectio_debug_phy phy(serial_clk,quad_clk,octet_clk,phy_reset,owner,
        1'b0,1'b1,1'b1,1'b0,1'b1,24'b0,,
        batch_mode ? batch_clk : clocks_out, batch_mode ? batch_data : data_out,
        batch_mode ? batch_release : release_out,rx,
        quad_clk,1'b0,1'b0,5'b0,5'b0,clk_pin,data_pin,tdi_pin,1'b1,,, , ,
        1'b0,4'b0,4'b0,4'b0,,1'b0,1'b0,serial_rx_clk,);
    swd200_link link(.clk(quad_clk),.reset(swd_reset),.rate(rate),
        .ack_sample(sample_slot[5:0]),.data_sample(sample_slot[5:0]),
        .idle_cycles(idle[3:0]),.release_guard(3'd0),.start(start),.enter_swd(1'b0),
        .header(header),.write_packet({^HOST_DATA,HOST_DATA}),
        .done(done),.ack(ack),.parity_error(parity_error),.read_data(read_data),
        .rx_slots(rx),.clk_slots(clocks_out),.data_slots(data_out),.release_slots(release_out));
    swd200_batch #(.SAME_CLOCK(1)) scheduler(.clk(quad_clk),.reset(swd_reset),.run(run_batch),
        .count(10'd2),.rate(rate),.ack_sample(sample_slot[5:0]),.data_sample(sample_slot[5:0]),
        .idle_cycles(idle[3:0]),.mode(7'd0),.command_addr(command_addr),.command_word(command_word),
        .payload_enabled(1'b0),.payload_data(32'b0),.write_result(batch_write),
        .result_addr(result_index),.result_word(batch_result),.completed(retired),.error(batch_error),
        .failed(batch_failed),.wait_retries(retries),.done(batch_done),.rx_slots(rx),
        .clk_slots(batch_clk),.data_slots(batch_data),.release_slots(batch_release));


    bit testing=0, reading, bad_parity, target_oe=0, target_bit=1;
    reg delayed_oe=0, delayed_bit=1;
    reg [2:0] target_ack;
    reg [31:0] target_data;
    int edges=0, limit, batch_index, last_index, received_reads;
    always @(posedge quad_clk) if(batch_mode && batch_write && result_index==0) begin
        if(batch_result!==TARGET_DATA) $fatal(1,"WAIT retry read result %h",batch_result);
        received_reads++;
    end

    task automatic next_response(input bit rd, input [2:0] result, input bit corrupt,
                                 input [31:0] data, input int tail);
        reading=rd;bad_parity=corrupt;target_ack=result;target_data=data;
        header=rd ? 8'h9f : 8'hbb; // AP DRW read/write, including request parity.
        edges=0;
        limit=(result==OK ? 46 : 13)+tail;
    endtask
    realtime last_rise, ack_rise, first_after_ack;
    always @(target_oe or target_bit) begin
        delayed_oe <= #(return_ns) target_oe;
        delayed_bit <= #(return_ns) target_bit;
    end
    assign data_pin = delayed_oe ? delayed_bit : 1'bz;
    // Change target output after the current rising edge and apply
    // the modeled return delay before presenting it to the pin.
    always @(posedge clk_pin) if(testing && clk_pin===1'b1) begin
        #0.001;
        target_oe=(edges>=9 && edges<=11) ||
                  (reading && target_ack==OK && edges>=12 && edges<=44);
        if(edges>=9 && edges<=11) target_bit=target_ack[edges-9];
        else if(edges>=12 && edges<=43) target_bit=target_data[edges-12];
        else target_bit=(^target_data) ^ bad_parity;
    end

    always @(target_oe or delayed_oe or phy.data_tri)
        if(testing && (target_oe || delayed_oe) && phy.data_tri===1'b0)
            $fatal(1,"SWDIO overlap after edge %0d",edges);
    always @(posedge clk_pin) if(testing && clk_pin===1'b1) begin
        if(last_rise!=0 && $realtime-last_rise<nominal_period-0.010)
            $fatal(1,"short SWCLK at edge %0d",edges+1);
        last_rise=$realtime;
        if(edges==limit) begin
            if(!batch_mode || batch_index==last_index) $fatal(1,"extra SWCLK after edge %0d",edges);
            batch_index++;
            if(batch_index==1) next_response(1,OK,0,TARGET_DATA,idle);
            else next_response(0,OK,0,0,idle==0 ? 2 : idle);
        end
        edges++;
        if(edges==12) ack_rise=$realtime;
        if(edges==13) begin
            first_after_ack=$realtime;
            if($test$plusargs("early_swd50") && sample_slot>=16 && first_after_ack-ack_rise!=20.0)
                $fatal(1,"missing early SWCLK after ACK: %0.3f ns",first_after_ack-ack_rise);
        end
        if(edges<=8) begin
            if(phy.data_tri!==0 || data_pin!==header[edges-1]) $fatal(1,"bad request at edge %0d",edges);
        end else if(target_ack==OK && !reading && edges>=14 && edges<=46) begin
            if(phy.data_tri!==0 ||
               data_pin!==(edges==46 ? ^HOST_DATA : HOST_DATA[edges-14]))
                $fatal(1,"bad write at edge %0d",edges);
        end else if(edges>(target_ack==OK ? 46 : 13)) begin
            if(phy.data_tri!==0 || data_pin!==0) $fatal(1,"bad idle at edge %0d",edges);
        end else if(phy.data_tri!==1) $fatal(1,"expected released SWDIO at edge %0d",edges);
    end

    task automatic transfer(input bit rd, input [2:0] result, input bit corrupt, input [31:0] data);
        @(negedge quad_clk);
        next_response(rd,result,corrupt,data,idle);
        testing=1;start=1;
        @(negedge quad_clk);start=0;
        do @(negedge quad_clk); while(!done);
        if(ack!==result || parity_error!==corrupt)
            $fatal(1,"read=%b ACK got=%b expected=%b parity got=%b expected=%b",rd,ack,result,parity_error,corrupt);
        if(rd && result==OK && read_data!==data)
            $fatal(1,"read data got=%h expected=%h",read_data,data);
        repeat(6) @(negedge quad_clk);
        if(edges!=limit) $fatal(1,"read=%b ACK=%b edges=%0d expected=%0d",rd,result,edges,limit);
        $display("SWD50_EDGE period_ns=%0.3f slot=%0d idle=%0d read=%b ack=%03b parity_error=%b d0=%b rises=%0d ack_to_next_ns=%0.3f",
                 nominal_period,sample_slot,idle,rd,result,corrupt,data[0],edges,first_after_ack-ack_rise);
        testing=0;
    endtask

    task automatic exercise_batch(input [2:0] first_ack, input bit corrupt);
        bit success;
        reg [3:0] expected_error;
        success=first_ack==WAIT_ACK;
        expected_error=success ? 4'b0 : {corrupt,first_ack};
        @(negedge quad_clk);
        batch_mode=1;
        batch_index=0;
        last_index=success ? 2 : 0;
        received_reads=0;
        next_response(1,first_ack,corrupt,TARGET_DATA,idle);
        testing=1;run_batch=1;
        do @(negedge quad_clk); while(!batch_done);
        if(batch_failed!==!success || batch_error!==expected_error || retries!==(success ? 16'd1 : 16'd0) ||
           retired!==(success ? 10'd2 : 10'd0) || received_reads!==(success ? 1 : 0))
            $fatal(1,"batch failed=%b error=%h retries=%d retired=%d results=%d",batch_failed,batch_error,retries,retired,received_reads);
        run_batch=0;
        repeat(6) @(negedge quad_clk);
        if(batch_index!=last_index || edges!=limit) $fatal(1,"batch wire count: transaction %d edge %d",batch_index,edges);
        $display("SWD50_BATCH first_ack=%03b parity_error=%b retries=%0d retired=%0d error=%h",
                 first_ack,corrupt,retries,retired,batch_error);
        testing=0;
    endtask

    initial begin
        if(VARIABLE_CLOCK) begin
            ref_ns=20.0;
            if($value$plusargs("fclk1_ns=%f",ref_ns)) begin end
            if(!$test$plusargs("half_rate")) rate=1;
            nominal_period=rate==0 ? ref_ns : ref_ns/2;
        end
        if($value$plusargs("sslot=%d",sample_slot)) begin end
        if($value$plusargs("idle=%d",idle)) begin end
        if($value$plusargs("return_ns=%f",return_ns)) begin end
        #300; resetn=1;
        wait(owner==1);released=1;wait(owner==3 && !swd_reset);
        transfer(1,OK,0,TARGET_DATA);
        transfer(0,WAIT_ACK,0,0);
        transfer(0,OK,0,0);
        transfer(1,FAULT_ACK,0,0);
        transfer(1,OK,1,~TARGET_DATA);
        transfer(1,WAIT_ACK,0,0);
        transfer(0,FAULT_ACK,0,0);
        transfer(1,OK,0,~TARGET_DATA);
        exercise_batch(WAIT_ACK,0);
        exercise_batch(FAULT_ACK,0);
        exercise_batch(OK,1);
        $display("SWD50_EDGES_PASS");
        $finish;
    end
    initial begin #100000; $fatal(1,"deadline owner=%0d edges=%0d",owner,edges); end
endmodule
