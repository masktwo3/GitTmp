module wide_sink (
    input wire [31:0] packed_word
);

    initial begin
        #1;
        $display("packed_word=%h", packed_word);
    end

endmodule
