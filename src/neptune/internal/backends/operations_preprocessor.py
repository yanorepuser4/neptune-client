#
# Copyright (c) 2022, Neptune Labs Sp. z o.o.
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
__all__ = ["OperationsPreprocessor"]

import dataclasses
import typing
from enum import Enum
from typing import (
    Callable,
    List,
    TypeVar,
)

from neptune.exceptions import MetadataInconsistency
from neptune.internal.exceptions import InternalClientError
from neptune.internal.operation import (
    AddStrings,
    AssignBool,
    AssignDatetime,
    AssignFloat,
    AssignInt,
    AssignString,
    ClearFloatLog,
    ClearStringLog,
    ClearStringSet,
    ConfigFloatSeries,
    CopyAttribute,
    DeleteAttribute,
    LogFloats,
    LogStrings,
    Operation,
    RemoveStrings,
)
from neptune.internal.operation_visitor import OperationVisitor
from neptune.internal.utils.paths import path_to_str

T = TypeVar("T")


class RequiresPreviousCompleted(Exception):
    """indicates that previous operations must be synchronized with server before preprocessing current one"""


@dataclasses.dataclass
class AccumulatedOperations:
    upload_operations: List[Operation] = dataclasses.field(default_factory=list)
    other_operations: List[Operation] = dataclasses.field(default_factory=list)

    errors: List[MetadataInconsistency] = dataclasses.field(default_factory=list)


class OperationsPreprocessor:
    def __init__(self):
        self._accumulators: typing.Dict[str, "_OperationsAccumulator"] = dict()
        self.processed_ops_count = 0

    def process(self, operations: List[Operation]):
        for op in operations:
            try:
                self._process_op(op)
                self.processed_ops_count += 1
            except RequiresPreviousCompleted:
                return

    def _process_op(self, op: Operation) -> "_OperationsAccumulator":
        path_str = path_to_str(op.path)
        target_acc = self._accumulators.setdefault(path_str, _OperationsAccumulator(op.path))
        target_acc.visit(op)
        return target_acc

    def get_operations(self) -> AccumulatedOperations:
        result = AccumulatedOperations()
        for _, acc in sorted(self._accumulators.items()):
            acc: "_OperationsAccumulator"
            for op in acc.get_operations():
                result.other_operations.append(op)
            result.errors.extend(acc.get_errors())

        return result


class _DataType(Enum):
    FLOAT = "Float"
    INT = "Int"
    BOOL = "Bool"
    STRING = "String"
    DATETIME = "Datetime"
    FLOAT_SERIES = "Float Series"
    STRING_SERIES = "String Series"
    STRING_SET = "String Set"


class _OperationsAccumulator(OperationVisitor[None]):
    def __init__(self, path: List[str]):
        self._path = path
        self._type: typing.Optional[_DataType] = None
        self._delete_ops = []
        self._modify_ops = []
        self._config_ops = []
        self._errors = []

    def get_operations(self) -> List[Operation]:
        return self._delete_ops + self._modify_ops + self._config_ops

    def get_errors(self) -> List[MetadataInconsistency]:
        return self._errors

    def _process_modify_op(
        self,
        expected_type: _DataType,
        op: Operation,
        modifier: Callable[[List[Operation], Operation], List[Operation]],
    ) -> None:

        if self._type and self._type != expected_type:
            # This case should never happen since inconsistencies on data types are verified on user api.
            # So such operations should not appear in the queue without delete operation between them.
            # Still we want to support this case to avoid some unclear dependencies and assumptions.
            self._errors.append(
                MetadataInconsistency(
                    "Cannot perform {} operation on {}: Attribute is not a {}".format(
                        op.__class__.__name__,
                        path_to_str(self._path),
                        expected_type.value,
                    )
                )
            )
        else:
            self._type = expected_type
            self._modify_ops = modifier(self._modify_ops, op)

    def _process_config_op(self, expected_type: _DataType, op: Operation) -> None:

        if self._type and self._type != expected_type:
            # This case should never happen since inconsistencies on data types are verified on user api.
            # So such operations should not appear in the queue without delete operation between them.
            # Still we want to support this case to avoid some unclear dependencies and assumptions.
            self._errors.append(
                MetadataInconsistency(
                    "Cannot perform {} operation on {}: Attribute is not a {}".format(
                        op.__class__.__name__,
                        path_to_str(self._path),
                        expected_type.value,
                    )
                )
            )
        else:
            self._type = expected_type
            self._config_ops = [op]

    def visit_assign_float(self, op: AssignFloat) -> None:
        self._process_modify_op(_DataType.FLOAT, op, self._assign_modifier())

    def visit_assign_int(self, op: AssignInt) -> None:
        self._process_modify_op(_DataType.INT, op, self._assign_modifier())

    def visit_assign_bool(self, op: AssignBool) -> None:
        self._process_modify_op(_DataType.BOOL, op, self._assign_modifier())

    def visit_assign_string(self, op: AssignString) -> None:
        self._process_modify_op(_DataType.STRING, op, self._assign_modifier())

    def visit_assign_datetime(self, op: AssignDatetime) -> None:
        self._process_modify_op(_DataType.DATETIME, op, self._assign_modifier())

    def visit_log_floats(self, op: LogFloats) -> None:
        self._process_modify_op(
            _DataType.FLOAT_SERIES,
            op,
            self._log_modifier(
                LogFloats,
                ClearFloatLog,
                lambda op1, op2: LogFloats(op1.path, op1.values + op2.values),
            ),
        )

    def visit_log_strings(self, op: LogStrings) -> None:
        self._process_modify_op(
            _DataType.STRING_SERIES,
            op,
            self._log_modifier(
                LogStrings,
                ClearStringLog,
                lambda op1, op2: LogStrings(op1.path, op1.values + op2.values),
            ),
        )

    def visit_clear_float_log(self, op: ClearFloatLog) -> None:
        self._process_modify_op(_DataType.FLOAT_SERIES, op, self._clear_modifier())

    def visit_clear_string_log(self, op: ClearStringLog) -> None:
        self._process_modify_op(_DataType.STRING_SERIES, op, self._clear_modifier())

    def visit_add_strings(self, op: AddStrings) -> None:
        self._process_modify_op(_DataType.STRING_SET, op, self._add_modifier())

    def visit_clear_string_set(self, op: ClearStringSet) -> None:
        self._process_modify_op(_DataType.STRING_SET, op, self._clear_modifier())

    def visit_remove_strings(self, op: RemoveStrings) -> None:
        self._process_modify_op(_DataType.STRING_SET, op, self._remove_modifier())

    def visit_config_float_series(self, op: ConfigFloatSeries) -> None:
        self._process_config_op(_DataType.FLOAT_SERIES, op)

    def visit_delete_attribute(self, op: DeleteAttribute) -> None:
        if self._type:
            if self._delete_ops:
                # Keep existing delete operation and simply clear all modification operations after it
                self._modify_ops = []
                self._config_ops = []
                self._type = None
            else:
                # This case is tricky. There was no delete operation, but some modifications was performed.
                # We do not know if this attribute exists on server side and we do not want a delete op to fail.
                # So we need to send a single modification before delete to be sure a delete op is valid.
                self._delete_ops = [self._modify_ops[0], op]
                self._modify_ops = []
                self._config_ops = []
                self._type = None
        else:
            if self._delete_ops:
                # Do nothing if there already is a delete operation
                # and no other operations was performed after it
                return
            else:
                # If value has not been set locally yet and no delete operation was performed,
                # simply perform single delete operation.
                self._delete_ops.append(op)

    def visit_copy_attribute(self, op: CopyAttribute) -> None:
        raise MetadataInconsistency("No CopyAttribute should reach accumulator")

    @staticmethod
    def _assign_modifier():
        return lambda ops, new_op: [new_op]

    @staticmethod
    def _clear_modifier():
        return lambda ops, new_op: [new_op]

    @staticmethod
    def _log_modifier(log_op_class: type, clear_op_class: type, log_combine: Callable[[T, T], T]):
        def modifier(ops, new_op):
            if len(ops) == 0:
                return [new_op]
            elif len(ops) == 1 and isinstance(ops[0], log_op_class):
                return [log_combine(ops[0], new_op)]
            elif len(ops) == 1 and isinstance(ops[0], clear_op_class):
                return [ops[0], new_op]
            elif len(ops) == 2:
                return [ops[0], log_combine(ops[1], new_op)]
            else:
                raise InternalClientError("Preprocessing operations failed: len(ops) == {}".format(len(ops)))

        return modifier

    @staticmethod
    def _add_modifier():
        # We do not optimize it on client side for now. It should not be often operation.
        return lambda ops, op: ops + [op]

    @staticmethod
    def _remove_modifier():
        # We do not optimize it on client side for now. It should not be often operation.
        return lambda ops, op: ops + [op]
