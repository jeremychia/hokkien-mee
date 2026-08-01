#!/usr/bin/env python3
"""Smoke test: print Python, torch, and CUDA info."""
import sys
try:
    import torch
except Exception:
    torch = None

print("Python:", sys.executable)
if torch is None:
    print("torch: not installed")
else:
    print("torch version:", torch.__version__)
    print("cuda available:", torch.cuda.is_available())
    try:
        print("cuda device count:", torch.cuda.device_count())
        print("current device:", torch.cuda.current_device())
        print("device name:", torch.cuda.get_device_name(torch.cuda.current_device()))
    except Exception:
        pass
