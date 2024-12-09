#!/bin/bash
# Copyright 2024 DeepMind Technologies Limited
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

export PYTHONPATH="$PYTHONPATH:$(pwd)"
source md4_venv/bin/activate

EXPT_DIR="$(pwd)"/expt
python md4/main.py \
  --config=md4/configs/md4/fineweb_edu.py \
  --sharded=false \
  --workdir=${EXPT_DIR}