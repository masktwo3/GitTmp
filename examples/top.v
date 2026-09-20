module top (
    input clk,
    input rst_n,
    output [3:0] status
);

    wire [31:0] w_u_mem_addr_in;
    wire w_u_mem_we;
    wire [31:0] w_u_mem_wdata;
    wire [31:0] w_u_cpu_rdata;

    cpu_core u_cpu (
        .clk(clk),
        .rst_n(rst_n),
        .addr_out(w_u_mem_addr_in),
        .we(w_u_mem_we),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_cpu_rdata),
        .status(status)
    );

    memory u_mem (
        .clk(clk),
        .rst_n(rst_n),
        .addr_in(w_u_mem_addr_in),
        .we(w_u_mem_we),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_cpu_rdata)
    );

endmodule
