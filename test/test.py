# SPDX-FileCopyrightText: © 2026 Mark Shilton
# SPDX-License-Identifier: Apache-2.0
#
# cocotb test suite for tt_um_aswarby_mac.
#
# Verification strategy: a pure-Python "golden" MAC mirrors the hardware's
# signed-INT8 multiply, INT32 saturating accumulate, weight-stationary load,
# and clear. Every hardware result is asserted against the golden model. The
# same suite re-runs unchanged against the synthesized gate-level netlist
# (GATES=yes), which is the Tiny Tapeout signoff gate.

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# Command encoding on uio_in[1:0]
CMD_NOP = 0
CMD_LOADW = 1
CMD_MAC = 2
CMD_CLEAR = 3

INT32_MAX = 2**31 - 1
INT32_MIN = -(2**31)

# The two saturation tests sweep ~131k MAC ops to drive the accumulator past the
# INT32 limit. That is fine at RTL (~50 s each) but would be punishingly slow at
# gate level, so they always skip under gate-level sim (GATES=yes) and can be
# skipped on demand with SKIP_SLOW=1.
_SKIP_SLOW = os.environ.get("SKIP_SLOW") == "1" or os.environ.get("GATES") == "yes"


# ----------------------------------------------------------------------------
# Golden model
# ----------------------------------------------------------------------------
class GoldenMac:
    """Bit-accurate reference for the hardware datapath."""

    def __init__(self):
        self.weight = 0
        self.acc = 0
        self.ovf = 0

    def load_w(self, data_s8):
        self.weight = data_s8

    def mac(self, data_s8):
        self.acc += data_s8 * self.weight
        if self.acc > INT32_MAX:
            self.acc = INT32_MAX
            self.ovf = 1
        elif self.acc < INT32_MIN:
            self.acc = INT32_MIN
            self.ovf = 1

    def clear(self):
        self.acc = 0
        self.ovf = 0


# ----------------------------------------------------------------------------
# Pin helpers
# ----------------------------------------------------------------------------
def s8_bits(v):
    """Two's-complement byte for a signed value in [-128, 127]."""
    return v & 0xFF


def uio_inputs(cmd=0, strobe=0, rd_sel=0):
    return (cmd & 3) | ((strobe & 1) << 2) | ((rd_sel & 3) << 3)


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


async def op(dut, cmd, data=0):
    """Present cmd+data, pulse strobe once, wait for the done flag, re-arm."""
    dut.ui_in.value = s8_bits(data)
    dut.uio_in.value = uio_inputs(cmd=cmd, strobe=0)
    await ClockCycles(dut.clk, 1)
    dut.uio_in.value = uio_inputs(cmd=cmd, strobe=1)
    # Wait for the done pulse (uio_out[5]); bounded so a hang fails loudly.
    # The MAC pipeline is 3 deep, so done arrives several cycles after strobe.
    seen_done = False
    for _ in range(16):
        await ClockCycles(dut.clk, 1)
        if (int(dut.uio_out.value) >> 5) & 1:
            seen_done = True
            break
    assert seen_done, f"no done pulse for cmd={cmd}"
    dut.uio_in.value = uio_inputs(cmd=cmd, strobe=0)
    await ClockCycles(dut.clk, 2)


async def read_acc(dut):
    """Stream the 32-bit accumulator out byte-by-byte and reassemble (signed)."""
    val = 0
    for i in range(4):
        dut.uio_in.value = uio_inputs(rd_sel=i)
        await ClockCycles(dut.clk, 1)
        val |= (int(dut.uo_out.value) & 0xFF) << (8 * i)
    if val >= 2**31:
        val -= 2**32
    return val


def ovf_flag(dut):
    return (int(dut.uio_out.value) >> 6) & 1


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------
@cocotb.test()
async def test_reset_zero(dut):
    await reset(dut)
    assert await read_acc(dut) == 0
    assert ovf_flag(dut) == 0


@cocotb.test()
async def test_basic_mac(dut):
    await reset(dut)
    await op(dut, CMD_LOADW, 3)
    await op(dut, CMD_MAC, 5)
    assert await read_acc(dut) == 15
    await op(dut, CMD_MAC, 5)
    assert await read_acc(dut) == 30
    await op(dut, CMD_CLEAR)
    assert await read_acc(dut) == 0


@cocotb.test()
async def test_signed(dut):
    await reset(dut)
    await op(dut, CMD_LOADW, -4)
    await op(dut, CMD_MAC, 7)        # -28
    assert await read_acc(dut) == -28
    await op(dut, CMD_MAC, -3)       # -28 + 12 = -16
    assert await read_acc(dut) == -16
    # New weight is stationary across subsequent activations.
    await op(dut, CMD_LOADW, -128)
    await op(dut, CMD_MAC, -128)     # -16 + 16384 = 16368
    assert await read_acc(dut) == 16368


@cocotb.test()
async def test_clear_resets_ovf(dut):
    await reset(dut)
    await op(dut, CMD_LOADW, 100)
    await op(dut, CMD_MAC, 100)      # 10000, no overflow
    assert ovf_flag(dut) == 0
    await op(dut, CMD_CLEAR)
    assert await read_acc(dut) == 0
    assert ovf_flag(dut) == 0


@cocotb.test()
async def test_random_sequence(dut):
    await reset(dut)
    gold = GoldenMac()
    rng = random.Random(7)
    await op(dut, CMD_CLEAR)
    gold.clear()
    for _ in range(150):
        choice = rng.random()
        if choice < 0.25:
            w = rng.randint(-128, 127)
            await op(dut, CMD_LOADW, w)
            gold.load_w(w)
        elif choice < 0.95:
            a = rng.randint(-128, 127)
            await op(dut, CMD_MAC, a)
            gold.mac(a)
        else:
            await op(dut, CMD_CLEAR)
            gold.clear()
        assert await read_acc(dut) == gold.acc, f"acc mismatch, expected {gold.acc}"
        assert ovf_flag(dut) == gold.ovf


@cocotb.test(skip=_SKIP_SLOW)
async def test_positive_saturation(dut):
    # weight=-128, data=-128 -> +16384 per MAC. 2^31 / 2^14 = 131072 MACs lands
    # exactly on +2^31, one past INT32_MAX, so the final add must clamp + flag.
    await reset(dut)
    gold = GoldenMac()
    await op(dut, CMD_CLEAR)
    gold.clear()
    await op(dut, CMD_LOADW, -128)
    gold.load_w(-128)

    base_mac = uio_inputs(cmd=CMD_MAC)
    dut.ui_in.value = s8_bits(-128)
    # 7-cycle period (2 high / 5 low) keeps ops spaced wider than the 3-deep
    # pipeline so each MAC fully commits before the next one's stage-2 read.
    N = 131072
    for _ in range(N):
        dut.uio_in.value = base_mac | (1 << 2)   # strobe high
        await ClockCycles(dut.clk, 2)
        dut.uio_in.value = base_mac              # strobe low (re-arm)
        await ClockCycles(dut.clk, 5)
        gold.mac(-128)

    assert gold.acc == INT32_MAX               # golden sanity: it saturated
    assert await read_acc(dut) == INT32_MAX
    assert ovf_flag(dut) == 1


@cocotb.test(skip=_SKIP_SLOW)
async def test_negative_saturation(dut):
    # weight=127, data=-128 -> -16256 per MAC. ~132137 MACs cross -2^31.
    await reset(dut)
    gold = GoldenMac()
    await op(dut, CMD_CLEAR)
    gold.clear()
    await op(dut, CMD_LOADW, 127)
    gold.load_w(127)

    base_mac = uio_inputs(cmd=CMD_MAC)
    dut.ui_in.value = s8_bits(-128)
    # Enough iterations to cross -2^31: ceil(2^31 / 16256) = 132137.
    # 7-cycle period (2 high / 5 low) keeps ops spaced wider than the pipeline.
    N = 132137
    for _ in range(N):
        dut.uio_in.value = base_mac | (1 << 2)
        await ClockCycles(dut.clk, 2)
        dut.uio_in.value = base_mac
        await ClockCycles(dut.clk, 5)
        gold.mac(-128)

    assert gold.acc == INT32_MIN
    assert await read_acc(dut) == INT32_MIN
    assert ovf_flag(dut) == 1
