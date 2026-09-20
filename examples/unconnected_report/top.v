module top (
    input clk,
    input rst_n
);

    wire [31:0] w_u_cpu_addr_out;
    wire [31:0] w_u_cpu_wdata;
    wire [31:0] w_u_cpu_rdata;

    cpu_core u_cpu (
        .clk(clk),
        .rst_n(rst_n),
        .addr_out(w_u_cpu_addr_out),
        .we(),
        .wdata(w_u_cpu_wdata),
        .rdata(w_u_cpu_rdata),
        .status()
    );

    memory u_mem (
        .clk(clk),
        .rst_n(rst_n),
        .addr_in(w_u_cpu_addr_out),
        .we(),
        .wdata(w_u_cpu_wdata),
        .rdata(w_u_cpu_rdata)
    );

endmodule
