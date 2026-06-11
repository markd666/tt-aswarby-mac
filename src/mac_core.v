/*
 * mac_core - signed INT8 x INT8 -> INT32 weight-stationary multiply-accumulate
 *
 * The compute atom of a quantized convolution: one weight is loaded and held
 * "stationary" while a stream of activation bytes is multiplied into a wide
 * accumulator. The accumulator add saturates at the INT32 limits so overflow
 * is well-defined, mirroring real fixed-point inference hardware.
 *
 * Copyright (c) 2026 Mark Shilton
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module mac_core (
    input  wire        clk,
    input  wire        rst_n,    // active-low reset
    input  wire        do_op,    // one-cycle strobe: execute `cmd` this cycle
    input  wire [1:0]  cmd,      // 00 NOP, 01 load weight, 10 MAC, 11 clear
    input  wire [7:0]  data,     // signed INT8 operand (weight or activation)
    input  wire [1:0]  rd_sel,   // which accumulator byte appears on rd_byte
    output wire [7:0]  rd_byte,  // selected accumulator byte (combinational)
    output wire        ovf       // sticky: accumulator has saturated since clear
);

  localparam [1:0] CMD_NOP   = 2'b00,
                   CMD_LOADW = 2'b01,
                   CMD_MAC   = 2'b10,
                   CMD_CLEAR = 2'b11;

  reg signed [7:0]  weight_q;
  reg signed [31:0] acc;
  reg               ovf_sticky;

  // Signed view of the input byte and the partial product.
  wire signed [7:0]  data_s  = data;                       // reinterpret as INT8
  wire signed [15:0] product = data_s * weight_q;          // signed 8x8 -> 16

  // 33-bit signed add headroom so we can detect INT32 overflow before clamping.
  wire signed [32:0] acc_se  = {acc[31], acc};
  wire signed [32:0] prod_se = {{17{product[15]}}, product};
  wire signed [32:0] sum     = acc_se + prod_se;

  localparam signed [32:0] SAT_MAX = 33'sd2147483647;      // +2^31 - 1
  localparam signed [32:0] SAT_MIN = -33'sd2147483648;     // -2^31

  always @(posedge clk) begin
    if (!rst_n) begin
      weight_q   <= 8'sd0;
      acc        <= 32'sd0;
      ovf_sticky <= 1'b0;
    end else if (do_op) begin
      case (cmd)
        CMD_LOADW: weight_q <= data_s;
        CMD_MAC: begin
          if (sum > SAT_MAX) begin
            acc        <= 32'sh7FFF_FFFF;
            ovf_sticky <= 1'b1;
          end else if (sum < SAT_MIN) begin
            acc        <= 32'sh8000_0000;
            ovf_sticky <= 1'b1;
          end else begin
            acc <= sum[31:0];
          end
        end
        CMD_CLEAR: begin
          acc        <= 32'sd0;
          ovf_sticky <= 1'b0;
        end
        default: ; // CMD_NOP - hold state
      endcase
    end
  end

  assign rd_byte = (rd_sel == 2'd0) ? acc[7:0]   :
                   (rd_sel == 2'd1) ? acc[15:8]  :
                   (rd_sel == 2'd2) ? acc[23:16] :
                                      acc[31:24];

  assign ovf = ovf_sticky;

endmodule
