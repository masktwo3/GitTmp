module top (
    input clk,
    input rst_n
);

    wire w_u_cpu_clk;
    wire w_u_mem_clk;
    wire w_u_cpu_rst_n;
    wire w_u_mem_rst_n;
    wire [31:0] w_u_mem_addr_in;
    wire [31:0] w_u_cpu_addr_out;
    wire [31:0] w_u_mem_wdata;
    wire [31:0] w_u_cpu_wdata;
    wire [31:0] w_u_cpu_rdata;
    wire [31:0] w_u_mem_rdata;

    assign w_u_cpu_clk = clk;
    assign w_u_mem_clk = clk;
    assign w_u_cpu_rst_n = rst_n;
    assign w_u_mem_rst_n = rst_n;
    assign w_u_mem_addr_in = w_u_cpu_addr_out;
    assign w_u_mem_wdata = w_u_cpu_wdata;
    assign w_u_cpu_rdata = w_u_mem_rdata;

    cpu_core u_cpu (
        .clk(w_u_cpu_clk),
        .rst_n(w_u_cpu_rst_n),
        .addr_out(w_u_cpu_addr_out),
        .we(),
        .wdata(w_u_cpu_wdata),
        .rdata(w_u_cpu_rdata),
        .status()
    );

    memory u_mem (
        .clk(w_u_mem_clk),
        .rst_n(w_u_mem_rst_n),
        .addr_in(w_u_mem_addr_in),
        .we(),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_mem_rdata)
    );

endmodule
