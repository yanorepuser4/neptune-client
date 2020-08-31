#
# Copyright (c) 2020, Neptune Labs Sp. z o.o.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from neptune.internal.backends.neptune_backend import NeptuneBackend
from neptune.internal.operation import Operation
from neptune.internal.operation_processor import OperationProcessor

# pylint: disable=protected-access


class SyncOperationProcessor(OperationProcessor):

    def __init__(self, backend: NeptuneBackend):
        self._backend = backend

    def enqueue_operation(self, op: Operation, wait: bool) -> None:
        # pylint: disable=unused-argument
        self._backend.execute_operations([op])

    def wait(self):
        pass