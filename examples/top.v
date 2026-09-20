module top (
    input clk,
    input rst_n,
    output [3:0] status
);

    wire w_u_cpu_clk;
    wire w_u_mem_clk;
    wire w_u_cpu_rst_n;
    wire w_u_mem_rst_n;
    wire [31:0] w_u_mem_addr_in;
    wire [31:0] w_u_cpu_addr_out;
    wire w_u_mem_we;
    wire w_u_cpu_we;
    wire [31:0] w_u_mem_wdata;
    wire [31:0] w_u_cpu_wdata;
    wire [31:0] w_u_cpu_rdata;
    wire [31:0] w_u_mem_rdata;
    wire [3:0] w_u_cpu_status;

    assign w_u_cpu_clk = clk;
    assign w_u_mem_clk = clk;
    assign w_u_cpu_rst_n = rst_n;
    assign w_u_mem_rst_n = rst_n;
    assign w_u_mem_addr_in = w_u_cpu_addr_out;
    assign w_u_mem_we = w_u_cpu_we;
    assign w_u_mem_wdata = w_u_cpu_wdata;
    assign w_u_cpu_rdata = w_u_mem_rdata;
    assign status = w_u_cpu_status;

    cpu_core u_cpu (
        .clk(w_u_cpu_clk),
        .rst_n(w_u_cpu_rst_n),
        .addr_out(w_u_cpu_addr_out),
        .we(w_u_cpu_we),
        .wdata(w_u_cpu_wdata),
        .rdata(w_u_cpu_rdata),
        .status(w_u_cpu_status)
    );

    memory u_mem (
        .clk(w_u_mem_clk),
        .rst_n(w_u_mem_rst_n),
        .addr_in(w_u_mem_addr_in),
        .we(w_u_mem_we),
        .wdata(w_u_mem_wdata),
        .rdata(w_u_mem_rdata)
    );

endmodule
