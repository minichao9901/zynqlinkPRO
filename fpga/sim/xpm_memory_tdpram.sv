// Portable test model for the exact synchronous read/byte-write mode used here.
module xpm_memory_tdpram #(
 parameter ADDR_WIDTH_A=10, ADDR_WIDTH_B=10, AUTO_SLEEP_TIME=0,
 BYTE_WRITE_WIDTH_A=8, BYTE_WRITE_WIDTH_B=8, CLOCKING_MODE="common_clock",
 MEMORY_INIT_FILE="none", MEMORY_INIT_PARAM="0", MEMORY_OPTIMIZATION="true",
 MEMORY_PRIMITIVE="block", MEMORY_SIZE=32768, MESSAGE_CONTROL=0,
 READ_DATA_WIDTH_A=32, READ_DATA_WIDTH_B=32, READ_LATENCY_A=1, READ_LATENCY_B=1,
 READ_RESET_VALUE_A="0", READ_RESET_VALUE_B="0", RST_MODE_A="SYNC", RST_MODE_B="SYNC",
 USE_MEM_INIT=0, WAKEUP_TIME="disable_sleep", WRITE_DATA_WIDTH_A=32,
 WRITE_DATA_WIDTH_B=32, WRITE_MODE_A="read_first", WRITE_MODE_B="read_first"
)(input clka, ena, input [3:0] wea, input [ADDR_WIDTH_A-1:0] addra,
 input [31:0] dina, output reg [31:0] douta, input rsta, regcea,
 input clkb, enb, input [3:0] web, input [ADDR_WIDTH_B-1:0] addrb,
 input [31:0] dinb, output reg [31:0] doutb, input rstb, regceb);
 reg [31:0] mem [0:MEMORY_SIZE/32-1];
 integer a,b;
 always @(posedge clka) if (ena) begin
   douta <= mem[addra];
   for(a=0;a<4;a=a+1) if(wea[a]) mem[addra][8*a+:8] <= dina[8*a+:8];
 end
 always @(posedge clkb) if (enb) begin
   doutb <= mem[addrb];
   for(b=0;b<4;b=b+1) if(web[b]) mem[addrb][8*b+:8] <= dinb[8*b+:8];
 end
endmodule
