module top (

);

    wire [31:0] packed_bus;
    wire [31:0] __slice_u_a_data;
    wire [31:0] __slice_u_b_data;

    assign packed_bus[15:8] = __slice_u_a_data[23:16];
    assign packed_bus[27:16] = __slice_u_b_data[15:4];

    wide_src_a u_a (
        .data(__slice_u_a_data)
    );

    wide_src_b u_b (
        .data(__slice_u_b_data)
    );

    wide_sink u_sink (
        .packed_word(packed_bus)
    );

endmodule
