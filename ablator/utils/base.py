import random
import sys
import typing as ty
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import numpy as np
import torch
from torch import nn
from pynvml.smi import nvidia_smi as smi


class Dummy:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, *args, **kwargs):
        return self

    def __getitem__(self, *args, **kwargs):
        return self


def iter_to_numpy(iterable):
    """
    Convert torch.Tensor elements to NumPy arrays.

    Parameters
    ----------
    iterable : Iterable
        The input iterable.

    Returns
    -------
    any
        The iterable with torch.Tensor elements replaced with their NumPy array equivalents.
    """
    return apply_lambda_to_iter(
        iterable,
        lambda v: v.detach().cpu().numpy() if isinstance(v, torch.Tensor) else v,
    )


def iter_to_device(
    data_dict, device
) -> ty.Union[Sequence[torch.Tensor], dict[str, torch.Tensor]]:
    """
    Convert torch.Tensor elements to the specified device.

    Parameters
    ----------
    data_dict : dict or list
        The input dictionary or list containing torch.Tensor elements.
    device : torch.device
        The target device for the tensors.

    Returns
    -------
    ty.Union[Sequence[torch.Tensor], dict[str, torch.Tensor]]
        The input data with tensors moved to the target device.
    """
    return apply_lambda_to_iter(
        data_dict, lambda v: v.to(device) if isinstance(v, torch.Tensor) else v
    )


def apply_lambda_to_iter(iterable, fn: Callable):
    """
    Applies a given function `fn` to each element of an iterable data structure.

    This function recursively applies `fn` to elements within nested dictionaries or lists.
    It can be used for converting torch.Tensor elements to NumPy arrays or moving tensors
    to a specified device.

    Parameters
    ----------
    iterable : Iterable
        The input iterable.
    fn : Callable
        The function to apply to each element.
        
    Returns
    -------
    any
        The resulting data structure after applying `fn` to each element of the input `iterable`.
        The type of the returned object matches the type of the input `iterable`.
    """
    if isinstance(iterable, dict):
        return {
            k: apply_lambda_to_iter(v, fn) if isinstance(v, (Iterable)) else fn(v)
            for k, v in iterable.items()
        }
    if isinstance(iterable, list):
        return [apply_lambda_to_iter(v, fn) for v in iterable]

    return fn(iterable)
    

def set_seed(seed: int):
    """
    Set the random seed.

    Parameters
    ----------
    seed : int
        The random seed to set.

    Returns
    -------
    int
        The set random seed.
    """
    assert seed is not None, "Must provide a seed"
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    return seed


def get_lr(optimizer):
    """
    Get the learning rate.

    Parameters
    ----------
    optimizer : torch.optim.Optimizer or dict
        The optimizer.

    Returns
    -------
    float
        The learning rate.
    """
    if isinstance(optimizer, dict):
        param_groups = optimizer["param_groups"]
    else:
        param_groups = optimizer.param_groups

    return param_groups[0]["lr"]


def debugger_is_active() -> bool:
    """
    Check if the debugger is currently active.

    Returns
    -------
    bool
        True if the debugger is active, False otherwise.
    
    Notes
    -----
    Return if the debugger is currently active
    """
    gettrace = getattr(sys, "gettrace", lambda: None)
    return gettrace() is not None


def get_latest_chkpts(checkpoint_dir: Path) -> list[Path]:
    """
    Get a list of the latest checkpoint files in a directory.

    Parameters
    ----------
    checkpoint_dir : Path
        The directory containing checkpoint files.

    Returns
    -------
    list[Path]
        A list of the latest checkpoint files sorted by their creation time.
    """
    return sorted(list(checkpoint_dir.glob("*.pt")))[::-1]


def parse_device(device: ty.Union[str, list[str]]):
    """
    Parse a device string or a list of device strings.

    Parameters
    ----------
    device : ty.Union[str, list[str]]
        The target device for the tensors.

    Returns
    -------
    any
        The parsed device string, integer, or list of device strings or integers.
    """
    if isinstance(device, str):
        if device in {"cpu", "cuda"}:
            return device
        if device.startswith("cuda:"):
            return device
        raise ValueError
    if isinstance(device, int):
        return device
    if isinstance(device, Iterable):
        return [parse_device(_device) for _device in device]

    return "cuda" if torch.cuda.is_available() else "cpu"


def init_weights(module: nn.Module):
    """
    Initialize the weights of a module.

    Parameters
    ----------
    module : nn.Module
        The input module to initialize.
    """
    if isinstance(module, nn.Linear):
        module.weight.data.normal_(mean=0.0, std=1.0)
        if module.bias is not None:
            module.bias.data.zero_()
    elif isinstance(module, nn.Embedding):
        module.weight.data.normal_(mean=0.0, std=1.0)
        if module.padding_idx is not None:
            module.weight.data[module.padding_idx].zero_()
    elif isinstance(module, nn.LayerNorm):
        module.bias.data.zero_()
        module.weight.data.fill_(1.0)


def get_gpu_max_mem() -> ty.List[int]:
    """
    Get the maximum memory of all available GPUs.

    Returns
    -------
    ty.List[int]
        A list of the maximum memory for each GPU.
    """
    return get_gpu_mem(mem_type="total")


def get_gpu_mem(
    mem_type: ty.Literal["used", "total", "free"] = "total"
) -> ty.List[int]:
    """
    Get the memory information of all available GPUs.

    Parameters
    ----------
    mem_type : ty.Literal["used", "total", "free"], optional
        The type of memory information to retrieve, by default "total".

    Returns
    -------
    ty.List[int]
        A list of memory values for each GPU, depending on the specified memory type.
    """
    # TODO: waiting for fix: https://github.com/pytorch/pytorch/issues/86493
    instance = smi.getInstance()
    memory = []
    for gpu in instance.DeviceQuery()["gpu"]:
        memory.append(gpu["fb_memory_usage"][mem_type])
    return memory
