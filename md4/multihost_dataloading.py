# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Multihost dataloading utilities.

Adapted from:
https://github.com/AI-Hypercomputer/maxtext/blob/main/MaxText/multihost_dataloading.py
"""

from collections.abc import Iterable, Iterator
import functools
import time
from typing import Union

import grain.python as grain
import jax
from jax.sharding import Mesh
from jax.sharding import NamedSharding
from jax.sharding import PartitionSpec
import jax.tree_util as jtu
import numpy as np
import tensorflow as tf  # pylint: disable=g-import-not-at-top


def _build_global_shape_and_sharding(
    local_shape: tuple[int, ...], global_mesh: Mesh
) -> tuple[tuple[int, ...], NamedSharding]:
  sharding = NamedSharding(global_mesh, PartitionSpec(global_mesh.axis_names))

  global_shape = (jax.process_count() * local_shape[0],) + local_shape[1:]

  return global_shape, sharding


def _form_global_array(path, array: np.ndarray, global_mesh: Mesh) -> jax.Array:
  """Put local sharded array into local devices."""
  global_shape, sharding = _build_global_shape_and_sharding(
      np.shape(array), global_mesh
  )

  try:
    local_device_arrays = np.split(
        array, len(global_mesh.local_devices), axis=0
    )
  except ValueError as array_split_error:
    raise ValueError(
        f"Unable to put to devices shape {array.shape} with "
        f"local device count {len(global_mesh.local_devices)} "
        f"at {jtu.keystr(path)}"
    ) from array_split_error

  local_device_buffers = jax.device_put(
      local_device_arrays, global_mesh.local_devices
  )
  return jax.make_array_from_single_device_arrays(
      global_shape, sharding, local_device_buffers
  )


def get_next_batch_sharded(
    local_iterator: Iterator[jax.Array], global_mesh: Mesh
) -> jax.Array:
  """Splits the host loaded data equally over all devices."""

  sleep_time = 10
  max_data_load_attempts = 30

  data_load_attempts = 0
  loaded_data_success = False
  while not loaded_data_success and data_load_attempts < max_data_load_attempts:
    data_load_attempts += 1
    try:
      local_data = next(local_iterator)
      loaded_data_success = True
    except tf.errors.FailedPreconditionError:
      print("Failed to get next data batch, retrying")
      time.sleep(sleep_time)

  # Try one last time, if this fails we will see the full stack trace.
  if not loaded_data_success:
    local_data = next(local_iterator)

  input_gdas = jtu.tree_map_with_path(
      functools.partial(_form_global_array, global_mesh=global_mesh), local_data
  )

  return input_gdas


class MultiHostDataLoadIterator:
  """fold get_next_batch_sharded into a iterator class."""

  def __init__(
      self,
      dataloader: Union[tf.data.Dataset, grain.DataLoader],
      global_mesh: Mesh,
  ):
    self.global_mesh = global_mesh
    self.dataloader = dataloader
    if isinstance(self.dataloader, tf.data.Dataset):
      self.local_iterator = self.dataloader.as_numpy_iterator()
    elif isinstance(self.dataloader, Iterable):
      self.local_iterator = iter(self.dataloader)
    else:
      raise ValueError(
          "Type error: dataloader should be either tf.data.Dataset or Iterable."
      )

  def reset(self):
    if isinstance(self.dataloader, tf.data.Dataset):
      self.local_iterator = self.dataloader.as_numpy_iterator()
    elif isinstance(self.dataloader, Iterable):
      self.local_iterator = iter(self.dataloader)
    else:
      raise ValueError(
          "Type error: dataloader should be either tf.data.Dataset or"
          " grain.DataLoader."
      )

  def __iter__(self):
    self.reset()
    return self

  def __next__(self):
    return get_next_batch_sharded(self.local_iterator, self.global_mesh)
