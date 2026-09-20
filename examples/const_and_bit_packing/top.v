module top (

);

    wire [31:0] w_u_a_data;
    wire [31:0] __slice_u_a_data;
    wire [31:0] __slice_u_b_data;

    assign w_u_a_data[31:28] = 4'hA;
    assign w_u_a_data[6:0] = 7'h55;
    assign w_u_a_data[15:8] = __slice_u_a_data[23:16];
    assign w_u_a_data[27:16] = __slice_u_b_data[15:4];

    wide_src_a u_a (
        .data(__slice_u_a_data)
    );

    wide_src_b u_b (
        .data(__slice_u_b_data)
    );

    flag_src u_flag (
        .flag(w_u_a_data[7])
    );

    wide_sink u_sink (
        .packed_word(w_u_a_data)
    );

endmodule
