import toolz
import os
import math
import warnings

import numpy as np

from multiprocessing import cpu_count
import pynvml


class CPUAffinity:
    def __init__(self, cores):
        self.cores = cores

    def setup(self, worker=None):
        os.sched_setaffinity(0, self.cores)


def unpack_bitmask(x, mask_bits=64):
    """Unpack a list of integers containing bitmasks.

    Parameters
    ----------
    x: list of int
        A list of integers
    mask_bits: int
        An integer determining the bitwidth of `x`

    Examples
    --------
    >>> from dask_cuda.utils import unpack_bitmaps
    >>> unpack_bitmask([1 + 2 + 8])
    [0, 1, 3]
    >>> unpack_bitmask([1 + 2 + 16])
    [0, 1, 4]
    >>> unpack_bitmask([1 + 2 + 16, 2 + 4])
    [0, 1, 4, 65, 66]
    >>> unpack_bitmask([1 + 2 + 16, 2 + 4], mask_bits=32)
    [0, 1, 4, 33, 34]
    """
    res = []

    for i, mask in enumerate(x):
        if not isinstance(mask, int):
            raise TypeError("All elements of the list `x` must be integers")

        cpu_offset = i * mask_bits

        bytestr = np.frombuffer(
            bytes(np.binary_repr(mask, width=mask_bits), "utf-8"), "u1"
        )
        mask = np.flip(bytestr - ord("0")).astype(np.bool)
        unpacked_mask = np.where(
            mask, np.arange(mask_bits) + cpu_offset, np.full(mask_bits, -1)
        )

        res += unpacked_mask[(unpacked_mask >= 0)].tolist()

    return res


@toolz.memoize
def get_cpu_count():
    return cpu_count()


@toolz.memoize
def get_gpu_count():
    pynvml.nvmlInit()
    return pynvml.nvmlDeviceGetCount()


def get_cpu_affinity(device_index):
    """Get a list containing the CPU indices to which a GPU is directly connected.

    Parameters
    ----------
    device_index: int
        Index of the GPU device

    Examples
    --------
    >>> from dask_cuda.utils import get_cpu_affinity
    >>> get_cpu_affinity(0)  # DGX-1 has GPUs 0-3 connected to CPUs [0-19, 20-39]
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
     40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59]
    >>> get_cpu_affinity(5)  # DGX-1 has GPUs 5-7 connected to CPUs [20-39, 60-79]
    [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39,
     60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79]
    >>> get_cpu_affinity(1000)  # DGX-1 has no device on index 1000
    dask_cuda/utils.py:96: UserWarning: Cannot get CPU affinity for device with index 1000, setting default affinity
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
     20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39,
     40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59,
     60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79]
    """
    pynvml.nvmlInit()

    try:
        # Result is a list of 64-bit integers, thus ceil(get_cpu_count() / 64)
        affinity = pynvml.nvmlDeviceGetCpuAffinity(
            pynvml.nvmlDeviceGetHandleByIndex(device_index), math.ceil(get_cpu_count() / 64)
        )
        return unpack_bitmask(affinity)
    except pynvml.NVMLError:
        warnings.warn(
            "Cannot get CPU affinity for device with index %d, setting default affinity"
            % device_index
        )
        return list(range(get_cpu_count()))


def get_n_gpus():
    try:
        return len(os.environ["CUDA_VISIBLE_DEVICES"].split(","))
    except KeyError:
        return get_gpu_count()


def get_device_total_memory(index=0):
    """
    Return total memory of CUDA device with index
    """
    pynvml.nvmlInit()
    return pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(index)).total
