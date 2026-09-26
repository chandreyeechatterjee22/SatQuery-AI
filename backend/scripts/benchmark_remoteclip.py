"""Measure RemoteCLIP load time, inference latency and process RAM on this machine.

Usage (PowerShell, from backend/):
    ..\\.venv\\Scripts\\python.exe scripts\\benchmark_remoteclip.py [image.tif]
"""
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import psutil  # noqa: E402


def rss_mb():
    return psutil.Process(os.getpid()).memory_info().rss / 2**20


def timed(fn, repeats):
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times), min(times), max(times)


def main():
    from PIL import Image

    from models import remoteclip
    from models.image_input import load_model_image

    base = rss_mb()
    t = time.perf_counter()
    import torch  # noqa: F401
    import open_clip  # noqa: F401
    import_s = time.perf_counter() - t
    after_import = rss_mb()

    t = time.perf_counter()
    enc = remoteclip.get_encoder()
    load_s = time.perf_counter() - t
    after_load = rss_mb()

    if len(sys.argv) > 1:
        image, _ = load_model_image(sys.argv[1], {"kind": "optical",
                                                  "roles": {"red": 1, "green": 2, "blue": 3}})
    else:
        image = Image.fromarray(np.random.default_rng(0).integers(0, 255, (256, 256, 3), dtype="uint8"))

    t = time.perf_counter()
    enc.encode_images([image])
    first_ms = (time.perf_counter() - t) * 1000
    img = timed(lambda: enc.encode_images([image]), 10)
    txt1 = timed(lambda: enc.encode_texts(["Is there a water area?"]), 10)
    prompts = [f"a satellite image of {i}" for i in range(30)]
    txt30 = timed(lambda: enc.encode_texts(prompts), 5)
    batch = [image] * 32
    img32 = timed(lambda: enc.encode_images(batch), 3)
    peak = rss_mb()

    print(f"torch threads            : {torch.get_num_threads()}")
    print(f"RAM baseline             : {base:7.0f} MB")
    print(f"RAM after torch import   : {after_import:7.0f} MB  (import {import_s:.1f} s)")
    print(f"RAM after model load     : {after_load:7.0f} MB  (load {load_s:.1f} s)")
    print(f"RAM after inference      : {peak:7.0f} MB")
    print(f"first image encode       : {first_ms:7.0f} ms")
    print(f"image encode (1)         : {img[0]:7.0f} ms median  [{img[1]:.0f}-{img[2]:.0f}]")
    print(f"image encode (batch 32)  : {img32[0]:7.0f} ms median  ({img32[0] / 32:.0f} ms/image)")
    print(f"text encode (1)          : {txt1[0]:7.0f} ms median")
    print(f"text encode (30 prompts) : {txt30[0]:7.0f} ms median")


if __name__ == "__main__":
    main()
