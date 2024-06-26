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
from neptune.exceptions import MetadataInconsistency
from neptune.internal.backends.operations_preprocessor import OperationsPreprocessor
from neptune.internal.operation import (
    AddStrings,
    AssignFloat,
    AssignString,
    ClearFloatLog,
    ClearStringSet,
    ConfigFloatSeries,
    DeleteAttribute,
    LogFloats,
    LogStrings,
    RemoveStrings,
)
from tests.unit.neptune.new.attributes.test_attribute_base import TestAttributeBase

FLog = LogFloats.ValueType
SLog = LogStrings.ValueType


class TestOperationsPreprocessor(TestAttributeBase):
    def test_delete_attribute(self):
        # given
        processor = OperationsPreprocessor()

        operations = [
            DeleteAttribute(["a"]),
            AssignFloat(["a"], 1),
            DeleteAttribute(["a"]),
            AssignString(["b"], "2"),
            DeleteAttribute(["b"]),
            AssignString(["c"], "2"),
            AssignString(["c"], "3"),
            DeleteAttribute(["c"]),
            DeleteAttribute(["d"]),
            DeleteAttribute(["d"]),
            DeleteAttribute(["e"]),
        ]

        # when
        processor.process(operations)

        # then
        result = processor.get_operations()
        self.assertEqual(result.upload_operations, [])
        self.assertEqual(
            result.other_operations,
            [
                DeleteAttribute(["a"]),
                AssignString(["b"], "2"),
                DeleteAttribute(["b"]),
                AssignString(["c"], "3"),
                DeleteAttribute(["c"]),
                DeleteAttribute(["d"]),
                DeleteAttribute(["e"]),
            ],
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(processor.processed_ops_count, len(operations))

    def test_assign(self):
        # given
        processor = OperationsPreprocessor()

        operations = [
            AssignFloat(["a"], 1),
            DeleteAttribute(["a"]),
            AssignString(["a"], "111"),
            DeleteAttribute(["b"]),
            AssignFloat(["b"], 2),
            AssignFloat(["c"], 3),
            AssignString(["c"], "333"),
            AssignString(["d"], "44"),
            AssignFloat(["e"], 5),
            AssignFloat(["e"], 10),
            AssignFloat(["e"], 33),
        ]

        # when
        processor.process(operations)

        # then
        result = processor.get_operations()
        self.assertEqual(result.upload_operations, [])
        self.assertEqual(
            result.other_operations,
            [
                AssignFloat(["a"], 1),
                DeleteAttribute(["a"]),
                AssignString(["a"], "111"),
                DeleteAttribute(["b"]),
                AssignFloat(["b"], 2),
                AssignFloat(["c"], 3),
                AssignString(["d"], "44"),
                AssignFloat(["e"], 33),
            ],
        )
        self.assertEqual(
            result.errors,
            [MetadataInconsistency("Cannot perform AssignString operation on c: Attribute is not a String")],
        )
        self.assertEqual(processor.processed_ops_count, len(operations))

    def test_series(self):
        # given
        processor = OperationsPreprocessor()

        operations = [
            LogFloats(["a"], [FLog(1, 2, 3)]),
            ConfigFloatSeries(["a"], min=7, max=70, unit="%"),
            DeleteAttribute(["a"]),
            LogStrings(["a"], [SLog("111", 3, 4)]),
            DeleteAttribute(["b"]),
            LogStrings(["b"], [SLog("222", None, 6)]),
            LogFloats(["c"], [FLog(1, 2, 3)]),
            LogFloats(["c"], [FLog(10, 20, 30), FLog(100, 200, 300)]),
            LogStrings(["d"], [SLog("4", 111, 222)]),
            ClearFloatLog(["e"]),
            AssignString(["h"], "44"),
            LogFloats(["h"], [FLog(10, 20, 30), FLog(100, 200, 300)]),
            LogFloats(["i"], [FLog(1, 2, 3)]),
            ConfigFloatSeries(["i"], min=7, max=70, unit="%"),
            ClearFloatLog(["i"]),
            LogFloats(["i"], [FLog(10, 20, 30), FLog(100, 200, 300)]),
        ]

        # when
        processor.process(operations)

        # then
        result = processor.get_operations()
        self.assertEqual(result.upload_operations, [])
        self.assertEqual(
            result.other_operations,
            [
                LogFloats(["a"], [FLog(1, 2, 3)]),
                DeleteAttribute(["a"]),
                LogStrings(["a"], [FLog("111", 3, 4)]),
                DeleteAttribute(["b"]),
                LogStrings(["b"], [SLog("222", None, 6)]),
                LogFloats(["c"], [FLog(1, 2, 3), FLog(10, 20, 30), FLog(100, 200, 300)]),
                LogStrings(["d"], [SLog("4", 111, 222)]),
                ClearFloatLog(["e"]),
                AssignString(["h"], "44"),
                ClearFloatLog(["i"]),
                LogFloats(["i"], [FLog(10, 20, 30), FLog(100, 200, 300)]),
                ConfigFloatSeries(["i"], min=7, max=70, unit="%"),
            ],
        )
        self.assertEqual(
            result.errors,
            [MetadataInconsistency("Cannot perform LogFloats operation on h: Attribute is not a Float Series")],
        )
        self.assertEqual(processor.processed_ops_count, len(operations))

    def test_sets(self):
        # given
        processor = OperationsPreprocessor()

        operations = [
            AddStrings(["a"], {"xx", "y", "abc"}),
            DeleteAttribute(["a"]),
            AddStrings(["a"], {"hhh", "gij"}),
            DeleteAttribute(["b"]),
            RemoveStrings(["b"], {"abc", "defgh"}),
            AddStrings(["c"], {"hhh", "gij"}),
            RemoveStrings(["c"], {"abc", "defgh"}),
            AddStrings(["c"], {"qqq"}),
            ClearStringSet(["d"]),
            RemoveStrings(["e"], {"abc", "defgh"}),
            AddStrings(["e"], {"qqq"}),
            ClearStringSet(["e"]),
            AddStrings(["f"], {"hhh", "gij"}),
            RemoveStrings(["f"], {"abc", "defgh"}),
            AddStrings(["f"], {"qqq"}),
            ClearStringSet(["f"]),
            AddStrings(["f"], {"xx", "y", "abc"}),
            RemoveStrings(["f"], {"abc", "defgh"}),
            AssignString(["h"], "44"),
            RemoveStrings(["h"], {""}),
            AssignFloat(["i"], 5),
            AddStrings(["i"], {""}),
        ]

        # when
        processor.process(operations)

        # then
        result = processor.get_operations()
        self.assertEqual(result.upload_operations, [])
        self.assertEqual(
            result.other_operations,
            [
                AddStrings(["a"], {"xx", "y", "abc"}),
                DeleteAttribute(["a"]),
                AddStrings(["a"], {"hhh", "gij"}),
                DeleteAttribute(["b"]),
                RemoveStrings(["b"], {"abc", "defgh"}),
                AddStrings(["c"], {"hhh", "gij"}),
                RemoveStrings(["c"], {"abc", "defgh"}),
                AddStrings(["c"], {"qqq"}),
                ClearStringSet(["d"]),
                ClearStringSet(["e"]),
                ClearStringSet(["f"]),
                AddStrings(["f"], {"xx", "y", "abc"}),
                RemoveStrings(["f"], {"abc", "defgh"}),
                AssignString(["h"], "44"),
                AssignFloat(["i"], 5),
            ],
        )
        self.assertEqual(
            result.errors,
            [
                MetadataInconsistency("Cannot perform RemoveStrings operation on h: Attribute is not a String Set"),
                MetadataInconsistency("Cannot perform AddStrings operation on i: Attribute is not a String Set"),
            ],
        )
        self.assertEqual(processor.processed_ops_count, len(operations))
