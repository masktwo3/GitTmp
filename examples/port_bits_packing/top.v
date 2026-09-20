module top (

);

    wire [31:0] w_u_sink_packed_word;
    wire [31:0] w_u_a_data;
    wire [31:0] w_u_b_data;

    assign w_u_sink_packed_word[15:8] = w_u_a_data[23:16];
    assign w_u_sink_packed_word[27:16] = w_u_b_data[15:4];

    wide_src_a u_a (
        .data(w_u_a_data)
    );

    wide_src_b u_b (
        .data(w_u_b_data)
    );

    wide_sink u_sink (
        .packed_word(w_u_sink_packed_word)
    );

endmodule
