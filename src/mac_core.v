/*
 * mac_core - signed INT8 x INT8 -> INT32 weight-stationary multiply-accumulate
 *
 * Pipelined datapath (to close timing at 50 MHz on the slow GF180 node, where a
 * single-cycle multiply + 33-bit accumulate is too long a combinational path):
 *
 *   stage 1  prod_q <= data * weight        (multiply only)
 *   stage 2  sum_q  <= acc + prod_q          (33-bit add only)
 *   stage 3  acc    <= saturate(sum_q)       (compare + clamp only)
 *
 * A MAC therefore commits to `acc` three cycles after its `do_op`. Operations
 * are issued one at a time via the strobe handshake (see mac_fsm), spaced far
 * enough apart that the pipeline always drains before the next op's stage-2
 * read of `acc`, so no forwarding/hazard logic is needed. load-weight and clear
 * act in stage 1 and are likewise spaced.
 *
 * Copyright (c) 2026 Mark Shilton
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module mac_core (
    input  wire        clk,
    input  wire        rst_n,    // active-low reset
    input  wire        do_op,    // one-cycle strobe: accept `cmd` this cycle
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

  localparam signed [32:0] SAT_MAX = 33'sd2147483647;   // +2^31 - 1
  localparam signed [32:0] SAT_MIN = -33'sd2147483648;  // -2^31

  reg signed [7:0]  weight_q;
  reg signed [31:0] acc;
  reg               ovf_sticky;

  // Pipeline registers + valid bits for the MAC path.
  reg               mac_v1, mac_v2;
  reg signed [15:0] prod_q;   // stage 1 result
  reg signed [32:0] sum_q;    // stage 2 result (pre-saturate, 33-bit headroom)

  wire signed [7:0] data_s = data;   // reinterpret input byte as INT8

  always @(posedge clk) begin
    if (!rst_n) begin
      weight_q   <= 8'sd0;
      acc        <= 32'sd0;
      ovf_sticky <= 1'b0;
      mac_v1     <= 1'b0;
      mac_v2     <= 1'b0;
      prod_q     <= 16'sd0;
      sum_q      <= 33'sd0;
    end else begin
      // Valid bits advance every cycle; default no new MAC.
      mac_v1 <= 1'b0;
      mac_v2 <= mac_v1;

      // ---- stage 0: accept an operation -------------------------------------
      if (do_op) begin
        case (cmd)
          CMD_LOADW: weight_q <= data_s;
          CMD_MAC: begin
            prod_q <= data_s * weight_q;   // stage 1: multiply
            mac_v1 <= 1'b1;
          end
          CMD_CLEAR: begin
            acc        <= 32'sd0;
            ovf_sticky <= 1'b0;
          end
          default: ; // NOP
        endcase
      end

      // ---- stage 2: 33-bit add (registered) ---------------------------------
      if (mac_v1)
        sum_q <= {acc[31], acc} + {{17{prod_q[15]}}, prod_q};

      // ---- stage 3: saturate + write back -----------------------------------
      if (mac_v2) begin
        if (sum_q > SAT_MAX) begin
          acc        <= 32'sh7FFF_FFFF;
          ovf_sticky <= 1'b1;
        end else if (sum_q < SAT_MIN) begin
          acc        <= 32'sh8000_0000;
          ovf_sticky <= 1'b1;
        end else begin
          acc <= sum_q[31:0];
        end
      end
    end
  end

  assign rd_byte = (rd_sel == 2'd0) ? acc[7:0]   :
                   (rd_sel == 2'd1) ? acc[15:8]  :
                   (rd_sel == 2'd2) ? acc[23:16] :
                                      acc[31:24];

  assign ovf = ovf_sticky;

endmodule
