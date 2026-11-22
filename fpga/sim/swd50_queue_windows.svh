    // Mirror selectio_swd50_drw and probe_stream's attached RTT queue.
    // The AXI/BRAM driver stands in for PS/CDMA; USB is outside these windows.
    localparam [31:0] SRAM_TEST=32'h20008000, RTT_DESC=32'h20008c00, RTT_RING=32'h20009000;
    localparam integer RTT_DESC_INDEX=(RTT_DESC-SRAM_TEST)/4, RTT_RING_INDEX=(RTT_RING-SRAM_TEST)/4;
    bit [8:0] template_count[1:2];
    reg [4:0] template_first[1:2];

    task automatic prepare_page(input bit writing, input [4:0] first_op,
                                input [31:0] address, input int words);
        int mode, old;
        reg [4:0] drw;
        mode=writing ? 2 : 1;
        drw=writing ? 13 : 15;
        write_reg('h1c,mode,0);
        old=template_count[mode];
        if(!old) for(int j=1;j<=256;j++) put(j,drw,0);
        if(!old || template_first[mode]!=first_op) begin
            put(0,first_op,address);
            template_first[mode]=first_op;
        end else if(first_op==5) write_reg('h1004,address,0);
        if(old!=words) begin
            if(old) for(int j=old+1;j<=old+2 && j<=256;j++) put(j,drw,0);
            put(words+1,14,0);
            put(words+2,6,0);
            template_count[mode]=words;
        end
    endtask

    task automatic memory_batch(input int words);
        reg [31:0] ctrlstat;
        batch(words+3);
        read_reg('h2000+4*(words+2),ctrlstat);
        if(ctrlstat & 'hb2) $fatal(1,"CTRL/STAT fence failed: %h",ctrlstat);
    endtask

    task automatic program_tar(input [31:0] address);
        write_reg('h1c,0,0);
        put(0,5,address);
        put(1,14,0);
        put(2,6,0);
        batch(3);
    endtask

    task automatic standard_sram;
        reg [31:0] read_tar;
        for(int j=0;j<512;j++) cm3.u_sys.mem[j]=32'hbadbad00;
        for(int j=0;j<256;j++) begin
            load_payload('h2000+4*j,pattern(j));
            load_payload('h2400+4*j,pattern(j));
        end

        program_tar(SRAM_TEST);
        prepare_page(1,14,0,256);
        wire_budget_begin();
        for(int page=0;page<2;page++) begin
            write_reg('h2c,4|page,0);
            memory_batch(256);
        end
        wire_budget_end(0,2048);
        write_reg('h1c,0,0);
        put(0,7,0);
        put(1,14,0);
        batch(2);
        read_reg('h2004,read_tar);
        if(read_tar!==SRAM_TEST && read_tar!==SRAM_TEST+2048)
            $fatal(1,"unexpected TAR after 512-word transfer: %h",read_tar);
        for(int j=0;j<512;j++)
            if(cm3.u_sys.mem[j]!==((j<256 || read_tar==SRAM_TEST+2048) ? pattern(j%256) : 32'hbadbad00))
                $fatal(1,"standard write SRAM word %0d",j);

        program_tar(SRAM_TEST);
        prepare_page(0,14,0,256);
        wire_budget_begin();
        for(int page=0;page<2;page++) begin
            write_reg('h2c,4|page,0);
            memory_batch(256);
        end
        wire_budget_end(1,2048);
        for(int page=0;page<2;page++)
            for(int j=0;j<256;j++) check_payload('h3000+page*1024+4*j,pattern(j));
        $display("STANDARD_SRAM_PASS words=512 batch_words=256 tar_after_write=%h",read_tar);
    endtask

    task automatic queued_rtt;
        int rd, next_rd, wr, available;
        reg [31:0] ring, size, live_rd;
        cm3.u_sys.mem[RTT_DESC_INDEX]=0;
        cm3.u_sys.mem[RTT_DESC_INDEX+1]=RTT_RING;
        cm3.u_sys.mem[RTT_DESC_INDEX+2]=8192;
        cm3.u_sys.mem[RTT_DESC_INDEX+3]=4096;
        cm3.u_sys.mem[RTT_DESC_INDEX+4]=6144;
        cm3.u_sys.mem[RTT_DESC_INDEX+5]=0;
        for(int j=0;j<2048;j++)
            cm3.u_sys.mem[RTT_RING_INDEX+j]=(j>=1024 && j<1536) ? 32'hbadbad00 : pattern(2048+j);
        rd=6144;
        // Prime the separate short-write bank as it is in steady state.
        prepare_page(1,5,RTT_DESC+16,1);
        wire_budget_begin();
        for(int packet=0;packet<4;packet++) begin
            if(packet==3) begin
                // Publish new producer data only after the preceding RdOff.
                @(negedge hclk);
                for(int j=1024;j<1536;j++) cm3.u_sys.mem[RTT_RING_INDEX+j]=pattern(2048+j);
                cm3.u_sys.mem[RTT_DESC_INDEX+3]=6144;
            end
            write_reg('h2c,0,0);
            prepare_page(0,5,RTT_DESC,6);
            memory_batch(6);
            read_reg('h200c,ring);
            read_reg('h2010,size);
            read_reg('h2014,wr);
            read_reg('h2018,live_rd);
            available=wr>=rd ? wr-rd : 8192-rd;
            if(ring!==RTT_RING || size!==8192 || live_rd!==rd || wr<0 || wr>=8192 || available<2048)
                $fatal(1,"invalid RTT descriptor ring=%h size=%d wr=%d rd=%d",ring,size,wr,live_rd);
            for(int page=0;page<2;page++) begin
                write_reg('h2c,4|page,0);
                prepare_page(0,5,ring+rd+page*1024,256);
                memory_batch(256);
            end
            // Stage and verify both payload banks before committing consumer progress.
            for(int page=0;page<2;page++)
                for(int j=0;j<256;j++)
                    check_payload('h3000+page*1024+4*j,pattern(2048+rd/4+page*256+j));
            next_rd=(rd+2048)%8192;
            write_reg('h2c,0,0);
            prepare_page(1,5,RTT_DESC+16,1);
            write_reg('h100c,next_rd,0);
            memory_batch(1);
            if(cm3.u_sys.mem[RTT_DESC_INDEX+4]!==next_rd)
                $fatal(1,"RTT RdOff commit %d expected=%d",cm3.u_sys.mem[RTT_DESC_INDEX+4],next_rd);
            $display("RTT_PACKET packet=%0d bytes=2048 old_rd=%0d confirmed_rd=%0d",
                     packet+1,rd,next_rd);
            rd=next_rd;
        end
        wire_budget_end(3,8192);
    endtask
