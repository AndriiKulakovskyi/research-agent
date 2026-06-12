---
name: pytorch-training
description: Patterns for implementing and training neural networks with PyTorch — device handling, training loops with AMP, checkpointing, evaluation, and reproducibility. Read before writing any model-training code.
---

# PyTorch training patterns

## Install

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121   # CUDA 12.x hosts
pip install torch                                                       # CPU-only hosts
```

Check `gpu_info` first; pick the matching wheel.

## Device handling (always device-agnostic)

```python
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = MyModel().to(device)
```

Never hardcode `"cuda"`. Move both model and every batch to `device`.

## Training loop with mixed precision and checkpointing

```python
from torch.amp import GradScaler, autocast

optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
scaler = GradScaler(enabled=device.type == "cuda")

for epoch in range(epochs):
    model.train()
    for x, y in train_loader:
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad(set_to_none=True)
        with autocast(device_type=device.type, enabled=device.type == "cuda"):
            loss = criterion(model(x), y)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

    torch.save(
        {"epoch": epoch, "model": model.state_dict(), "optimizer": optimizer.state_dict()},
        f"checkpoints/epoch_{epoch:03d}.pt",
    )
```

## Evaluation

```python
model.eval()
with torch.no_grad():
    ...
```

Report metrics with uncertainty where possible (k-fold or repeated runs), and
always compare against a sensible baseline (majority class, linear model).

## Reproducibility

```python
torch.manual_seed(7); import random, numpy as np
random.seed(7); np.random.seed(7)
```

## Workflow rules

1. Run `gpu_info` before writing code; choose batch size to fit reported VRAM.
2. Train via a script in the workspace (`execute`), never inline — save the
   script, metrics (JSON/CSV), curves (matplotlib PNG), and checkpoints to files.
3. Start with a small subset + 1 epoch to validate the pipeline end to end,
   then scale up.
4. If CUDA runs out of memory: halve the batch size, use gradient
   accumulation, or reduce model width — in that order.
