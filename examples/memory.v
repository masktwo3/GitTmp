module memory(clk, rst_n, addr_in, we, wdata, rdata);
    input clk;
    input rst_n;
    input [31:0] addr_in;
    input we;
    input [31:0] wdata;
    output [31:0] rdata;

    // dummy body for example purposes
    assign rdata = 32'h0;

endmodule
