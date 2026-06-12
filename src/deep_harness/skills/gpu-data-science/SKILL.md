---
name: gpu-data-science
description: GPU-accelerated dataframes and classical ML with NVIDIA RAPIDS (cuDF, cuML), including zero-code pandas acceleration and CPU fallbacks. Read before large-scale data processing or classical ML on a GPU host.
---

# GPU data science with RAPIDS

RAPIDS gives pandas/sklearn-style APIs on the GPU. Use it when `gpu_info`
reports an NVIDIA GPU and the data is large enough to matter (≳100 MB or
≳1M rows); otherwise plain pandas/sklearn is simpler and fast enough.

## Install (CUDA 12.x)

```bash
pip install cudf-cu12 cuml-cu12 --extra-index-url=https://pypi.nvidia.com
```

## Zero-code acceleration (preferred first step)

`cudf.pandas` accelerates existing pandas code, falling back to CPU for
unsupported ops:

```bash
python -m cudf.pandas analysis.py     # run any pandas script GPU-accelerated
```

or at the top of a script, before importing pandas:

```python
import cudf.pandas
cudf.pandas.install()
import pandas as pd   # now GPU-backed
```

## Direct cuDF / cuML

```python
import cudf
df = cudf.read_csv("orders.csv")                  # pandas-like API on GPU
revenue = df.groupby("category")["total_amount"].sum()

from cuml.cluster import KMeans                    # sklearn-like API on GPU
km = KMeans(n_clusters=8).fit(features)
```

`cuml.accel` does the same zero-code trick for sklearn:
`python -m cuml.accel train.py`.

## CPU fallback pattern

Keep analyses runnable everywhere:

```python
try:
    import cudf as xpd
    GPU = True
except ImportError:
    import pandas as xpd
    GPU = False
```

## Workflow rules

1. Run `gpu_info` first; only install RAPIDS wheels when a GPU is present.
2. Move data to/from the GPU as little as possible; do the whole pipeline in
   cuDF, convert with `.to_pandas()` only for plotting/export.
3. Validate GPU results against a small pandas/sklearn run before trusting
   them (dtype and NaN-handling differences exist).
4. Save outputs (datasets, figures, metrics) to workspace files and report paths.
