#!/usr/bin/env python3
# SPDX-FileCopyrightText: © 2026 Mark Shilton
# SPDX-License-Identifier: Apache-2.0
"""
Generate INT8 MAC test vectors and their golden INT32 result.

This is the small traceability link back to the aswarby detector work: instead
of hand-rolled stimulus, the cocotb suite can be pointed at vectors derived
from a real quantized layer. By default this emits a self-contained random row;
pass --from-npy to pull one (weights, activations) row out of a saved INT8
checkpoint export (e.g. a Hailo-quantized v5.x conv layer) once one exists.

The output JSON mirrors exactly what mac_core.v computes:
    acc = clamp_int32( sum_i weight[i] * activation[i] )

Usage:
    python tools/export_vectors.py --n 16 --seed 7 --out vectors.json
    python tools/export_vectors.py --from-npy layer.npz --row 0 --out vectors.json
"""
import argparse
import json
import sys

INT32_MAX = 2**31 - 1
INT32_MIN = -(2**31)


def golden_mac(weights, activations):
    """Bit-accurate reference matching the hardware's saturating accumulate."""
    assert len(weights) == len(activations)
    acc = 0
    ovf = 0
    for w, a in zip(weights, activations):
        acc += int(w) * int(a)
        if acc > INT32_MAX:
            acc, ovf = INT32_MAX, 1
        elif acc < INT32_MIN:
            acc, ovf = INT32_MIN, 1
    return acc, ovf


def random_row(n, seed):
    import random

    rng = random.Random(seed)
    weights = [rng.randint(-128, 127) for _ in range(n)]
    activations = [rng.randint(-128, 127) for _ in range(n)]
    return weights, activations


def npy_row(path, row):
    import numpy as np

    data = np.load(path)
    w = np.asarray(data["weights"], dtype=np.int64)
    a = np.asarray(data["activations"], dtype=np.int64)
    if w.ndim > 1:
        w = w[row]
    if a.ndim > 1:
        a = a[row]
    if not ((-128 <= w).all() and (w <= 127).all()):
        sys.exit("weights are not INT8 — quantize the layer before exporting")
    if not ((-128 <= a).all() and (a <= 127).all()):
        sys.exit("activations are not INT8 — quantize before exporting")
    return w.tolist(), a.tolist()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=16, help="row length for random mode")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--from-npy", default=None, help="npz with 'weights' and 'activations'")
    p.add_argument("--row", type=int, default=0)
    p.add_argument("--out", default="-", help="output path or - for stdout")
    args = p.parse_args()

    if args.from_npy:
        weights, activations = npy_row(args.from_npy, args.row)
    else:
        weights, activations = random_row(args.n, args.seed)

    acc, ovf = golden_mac(weights, activations)
    doc = {
        "weights": weights,
        "activations": activations,
        "golden_acc": acc,
        "golden_ovf": ovf,
        "note": "acc = clamp_int32(sum weight[i]*activation[i]); matches mac_core.v",
    }
    text = json.dumps(doc, indent=2)
    if args.out == "-":
        print(text)
    else:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}: {len(weights)} taps, golden_acc={acc}, ovf={ovf}")


if __name__ == "__main__":
    main()
