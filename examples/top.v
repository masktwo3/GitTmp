module top (
    input clk,
    input rst_n,
    output [3:0] status
);

    wire [31:0] addr;
    wire we;
    wire [31:0] wdata;
    wire [31:0] rdata;

    cpu_core u_cpu (
        .clk(clk),
        .rst_n(rst_n),
        .addr_out(addr),
        .we(we),
        .wdata(wdata),
        .rdata(rdata),
        .status(status)
    );

    memory u_mem (
        .clk(clk),
        .rst_n(rst_n),
        .addr_in(addr),
        .we(we),
        .wdata(wdata),
        .rdata(rdata)
    );

endmodule
