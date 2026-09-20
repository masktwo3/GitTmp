module top (
    input clk,
    input rst_n
);

    wire [31:0] w_u_mem_addr_in;
    wire [31:0] w_u_mem_wdata;
    wire [31:0] w_u_cpu_rdata;

    cpu_core u_cpu (
        .clk(clk),
        .rst_n(rst_n),
        .addr_out(w_u_mem_addr_in),
        .we(),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_cpu_rdata),
        .status()
    );

    memory u_mem (
        .clk(clk),
        .rst_n(rst_n),
        .addr_in(w_u_mem_addr_in),
        .we(),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_cpu_rdata)
    );

endmodule
