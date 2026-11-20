`timescale 1ns/1ps
module tb_selectio_uart_tx;
    bit clk=0,reset=1,start=0;
    always #5 clk=!clk;
    reg [31:0] period,d,ram[0:1023];
    wire [9:0] addr;
    wire [3:0] slots;
    wire done,valid,error;
    wire [7:0] data;
    reg [12:0] length;
    integer received;
    selectio_uart_tx tx(clk,reset,start,length,period,d,addr,slots,,done);
    selectio_uart_rx rx(clk,reset,1'b1,slots,period,valid,data,error);
    always @(posedge clk) d<=ram[addr];
    always @(negedge clk) if(!reset)begin
        if(error)$fatal(1,"UART framing");
        if(valid)begin
            if(data!==ram[received>>2][(received&3)*8+:8])$fatal(1,"UART word byte %d got %h",received,data);
            received++;
        end
    end
    task automatic trial(input int p,n);
        @(negedge clk);reset=1;
        for(integer i=0;i<(n+3)/4;i++)ram[i]=$random;
        period=p;length=n;received=0;repeat(6)@(negedge clk);reset=0;repeat(5)@(negedge clk);
        start=1;@(negedge clk);start=0;wait(done);repeat(10)@(negedge clk);
        if(received!=n)$fatal(1,"UART length");
        $display("UART_TX_PASS period=%d bytes=%d",p,n);
    endtask
    initial begin trial(1024,4096);trial(888889,8);$finish;end
    initial begin #3000000;$fatal(1,"timeout");end
endmodule
