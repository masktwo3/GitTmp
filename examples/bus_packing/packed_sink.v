module packed_sink (
    input wire [31:0] packed_word   // reads the fully assembled 32-bit bus
);

    initial begin
        #1;
        $display("packed_word=%h", packed_word);
    end

endmodule
