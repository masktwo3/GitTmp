module cpu_core (
    input  wire        clk,
    input  wire        rst_n,
    output wire [31:0] addr_out,
    output wire        we,
    output wire [31:0] wdata,
    input  wire [31:0] rdata,
    output wire [3:0]  status
);

    // dummy body for example purposes
    assign addr_out = 32'h0;
    assign we        = 1'b0;
    assign wdata      = 32'h0;
    assign status      = 4'h0;

endmodule
