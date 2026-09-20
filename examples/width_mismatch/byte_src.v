module byte_src (
    output wire [7:0] status,   // auto-extended into a wider net (no bits column needed)
    output wire [7:0] lane_a,   // explicitly placed at bus[7:0]
    output wire [7:0] lane_b    // explicitly placed at bus[23:16]
);

    assign status = 8'hAA;
    assign lane_a  = 8'h11;
    assign lane_b  = 8'h22;

endmodule
