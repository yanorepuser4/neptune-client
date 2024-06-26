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
__all__ = ["NeptuneBackendMock"]

import uuid
from collections import defaultdict
from datetime import datetime
from typing import (
    Any,
    Dict,
    Generator,
    Iterable,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from neptune.api.models import (
    BoolField,
    DateTimeField,
    Field,
    FieldDefinition,
    FieldType,
    FloatField,
    FloatPointValue,
    FloatSeriesField,
    FloatSeriesValues,
    IntField,
    LeaderboardEntry,
    NextPage,
    QueryFieldDefinitionsResult,
    QueryFieldsResult,
    StringField,
    StringPointValue,
    StringSeriesField,
    StringSeriesValues,
    StringSetField,
)
from neptune.core.components.operation_storage import OperationStorage
from neptune.exceptions import (
    ContainerUUIDNotFound,
    MetadataInconsistency,
    ModelVersionNotFound,
    ProjectNotFound,
    RunNotFound,
)
from neptune.internal.backends.api_model import (
    ApiExperiment,
    Project,
    Workspace,
)
from neptune.internal.backends.neptune_backend import NeptuneBackend
from neptune.internal.backends.nql import NQLQuery
from neptune.internal.container_structure import ContainerStructure
from neptune.internal.container_type import ContainerType
from neptune.internal.exceptions import (
    InternalClientError,
    NeptuneException,
)
from neptune.internal.id_formats import (
    QualifiedName,
    SysId,
    UniqueId,
)
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
from neptune.internal.utils.generic_attribute_mapper import NoValue
from neptune.internal.utils.paths import path_to_str
from neptune.types import (
    Boolean,
    Integer,
)
from neptune.types.atoms.datetime import Datetime
from neptune.types.atoms.float import Float
from neptune.types.atoms.string import String
from neptune.types.namespace import Namespace
from neptune.types.series.float_series import FloatSeries
from neptune.types.series.string_series import StringSeries
from neptune.types.sets.string_set import StringSet
from neptune.types.value import Value
from neptune.types.value_visitor import ValueVisitor
from neptune.typing import ProgressBarType

Val = TypeVar("Val", bound=Value)


class NeptuneBackendMock(NeptuneBackend):
    WORKSPACE_NAME = "mock-workspace"
    PROJECT_NAME = "project-placeholder"
    PROJECT_KEY = SysId("OFFLINE")
    MODEL_SYS_ID = SysId("OFFLINE-MOD")

    def __init__(self, credentials=None, proxies=None):
        self._project_id: UniqueId = UniqueId(str(uuid.uuid4()))
        self._containers: Dict[(UniqueId, ContainerType), ContainerStructure[Value, dict]] = dict()
        self._next_run = 1  # counter for runs
        self._next_model_version = defaultdict(lambda: 1)  # counter for model versions
        self._attribute_type_converter_value_visitor = self.AttributeTypeConverterValueVisitor()
        self._create_container(self._project_id, ContainerType.PROJECT, self.PROJECT_KEY)

    def get_available_projects(
        self, workspace_id: Optional[str] = None, search_term: Optional[str] = None
    ) -> List[Project]:
        return [
            Project(
                id=UniqueId(str(uuid.uuid4())),
                name=self.PROJECT_NAME,
                workspace=self.WORKSPACE_NAME,
                sys_id=self.PROJECT_KEY,
            )
        ]

    def get_available_workspaces(self) -> List[Workspace]:
        return [Workspace(id=UniqueId(str(uuid.uuid4())), name=self.WORKSPACE_NAME)]

    def _create_container(self, container_id: UniqueId, container_type: ContainerType, sys_id: SysId):
        container = self._containers.setdefault((container_id, container_type), ContainerStructure[Value, dict]())
        container.set(["sys", "id"], String(str(sys_id)))
        container.set(["sys", "state"], String("Active"))
        container.set(["sys", "owner"], String("offline_user"))
        container.set(["sys", "size"], Float(0))
        container.set(["sys", "tags"], StringSet(set()))
        container.set(["sys", "creation_time"], Datetime(datetime.now()))
        container.set(["sys", "modification_time"], Datetime(datetime.now()))
        container.set(["sys", "failed"], Boolean(False))
        if container_type == ContainerType.MODEL_VERSION:
            container.set(["sys", "model_id"], String(str(self.MODEL_SYS_ID)))
            container.set(["sys", "stage"], String("none"))
        return container

    def _get_container(self, container_id: UniqueId, container_type: ContainerType):
        key = (container_id, container_type)
        if key not in self._containers:
            raise ContainerUUIDNotFound(container_id, container_type)
        container = self._containers[(container_id, container_type)]
        return container

    def create_run(
        self,
        project_id: UniqueId,
        custom_run_id: Optional[str] = None,
        notebook_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
    ) -> ApiExperiment:
        sys_id = SysId(f"{self.PROJECT_KEY}-{self._next_run}")
        self._next_run += 1
        new_run_id = UniqueId(str(uuid.uuid4()))
        self._create_container(new_run_id, ContainerType.RUN, sys_id=sys_id)
        return ApiExperiment(
            id=new_run_id,
            type=ContainerType.RUN,
            sys_id=sys_id,
            workspace=self.WORKSPACE_NAME,
            project_name=self.PROJECT_NAME,
            trashed=False,
        )

    def create_model(self, project_id: str, key: str) -> ApiExperiment:
        sys_id = SysId(f"{self.PROJECT_KEY}-{key}")
        new_run_id = UniqueId(str(uuid.uuid4()))
        self._create_container(new_run_id, ContainerType.MODEL, sys_id=sys_id)
        return ApiExperiment(
            id=new_run_id,
            type=ContainerType.MODEL,
            sys_id=sys_id,
            workspace=self.WORKSPACE_NAME,
            project_name=self.PROJECT_NAME,
            trashed=False,
        )

    def create_model_version(self, project_id: str, model_id: UniqueId) -> ApiExperiment:
        try:
            model_key = self._get_container(container_id=model_id, container_type=ContainerType.MODEL).get("sys/id")
        except ContainerUUIDNotFound:
            model_key = "MOD"

        sys_id = SysId(f"{self.PROJECT_KEY}-{model_key}-{self._next_model_version[model_id]}")
        self._next_model_version[model_id] += 1
        new_run_id = UniqueId(str(uuid.uuid4()))
        self._create_container(new_run_id, ContainerType.MODEL_VERSION, sys_id=sys_id)
        return ApiExperiment(
            id=new_run_id,
            type=ContainerType.MODEL,
            sys_id=sys_id,
            workspace=self.WORKSPACE_NAME,
            project_name=self.PROJECT_NAME,
            trashed=False,
        )

    def get_project(self, project_id: QualifiedName) -> Project:
        return Project(
            id=self._project_id,
            name=self.PROJECT_NAME,
            workspace=self.WORKSPACE_NAME,
            sys_id=self.PROJECT_KEY,
        )

    def get_metadata_container(
        self,
        container_id: Union[UniqueId, QualifiedName],
        expected_container_type: Optional[ContainerType],
    ) -> ApiExperiment:
        if "/" not in container_id:
            raise ValueError("Backend mock expect container_id as QualifiedName only")

        if expected_container_type == ContainerType.RUN:
            raise RunNotFound(container_id)
        elif expected_container_type == ContainerType.MODEL:
            return ApiExperiment(
                id=UniqueId(str(uuid.uuid4())),
                type=ContainerType.MODEL,
                sys_id=SysId(container_id.rsplit("/", 1)[-1]),
                workspace=self.WORKSPACE_NAME,
                project_name=self.PROJECT_NAME,
            )
        elif expected_container_type == ContainerType.MODEL_VERSION:
            raise ModelVersionNotFound(container_id)
        else:
            raise ProjectNotFound(container_id)

    def execute_operations(
        self,
        container_id: UniqueId,
        container_type: ContainerType,
        operations: List[Operation],
        operation_storage: OperationStorage,
    ) -> Tuple[int, List[NeptuneException]]:
        result = []
        for op in operations:
            try:
                self._execute_operation(container_id, container_type, op, operation_storage)
            except NeptuneException as e:
                result.append(e)
        return len(operations), result

    def _execute_operation(
        self, container_id: UniqueId, container_type: ContainerType, op: Operation, operation_storage: OperationStorage
    ) -> None:
        run = self._get_container(container_id, container_type)
        val = run.get(op.path)
        if val is not None and not isinstance(val, Value):
            if isinstance(val, dict):
                raise MetadataInconsistency("{} is a namespace, not an attribute".format(op.path))
            else:
                raise InternalClientError("{} is a {}".format(op.path, type(val)))
        visitor = NeptuneBackendMock.NewValueOpVisitor(self, op.path, val, operation_storage)
        new_val = visitor.visit(op)
        if new_val is not None:
            run.set(op.path, new_val)
        else:
            run.pop(op.path)

    def get_attributes(self, container_id: str, container_type: ContainerType) -> List[FieldDefinition]:
        run = self._get_container(container_id, container_type)
        return list(self._generate_attributes(None, run.get_structure()))

    def _generate_attributes(self, base_path: Optional[str], values: dict):
        for key, value_or_dict in values.items():
            new_path = base_path + "/" + key if base_path is not None else key
            if isinstance(value_or_dict, dict):
                yield from self._generate_attributes(new_path, value_or_dict)
            else:
                yield FieldDefinition(
                    new_path,
                    value_or_dict.accept(self._attribute_type_converter_value_visitor),
                )

    def get_float_attribute(self, container_id: str, container_type: ContainerType, path: List[str]) -> FloatField:
        val = self._get_attribute(container_id, container_type, path, Float)
        return FloatField(path=path_to_str(path), value=val.value)

    def get_int_attribute(self, container_id: str, container_type: ContainerType, path: List[str]) -> IntField:
        val = self._get_attribute(container_id, container_type, path, Integer)
        return IntField(path=path_to_str(path), value=val.value)

    def get_bool_attribute(self, container_id: str, container_type: ContainerType, path: List[str]) -> BoolField:
        val = self._get_attribute(container_id, container_type, path, Boolean)
        return BoolField(path=path_to_str(path), value=val.value)

    def get_string_attribute(self, container_id: str, container_type: ContainerType, path: List[str]) -> StringField:
        val = self._get_attribute(container_id, container_type, path, String)
        return StringField(path=path_to_str(path), value=val.value)

    def get_datetime_attribute(
        self, container_id: str, container_type: ContainerType, path: List[str]
    ) -> DateTimeField:
        val = self._get_attribute(container_id, container_type, path, Datetime)
        return DateTimeField(path=path_to_str(path), value=val.value)

    def get_float_series_attribute(
        self, container_id: str, container_type: ContainerType, path: List[str]
    ) -> FloatSeriesField:
        val = self._get_attribute(container_id, container_type, path, FloatSeries)
        return FloatSeriesField(path=path_to_str(path), last=val.values[-1] if val.values else None)

    def get_string_series_attribute(
        self, container_id: str, container_type: ContainerType, path: List[str]
    ) -> StringSeriesField:
        val = self._get_attribute(container_id, container_type, path, StringSeries)
        return StringSeriesField(path=path_to_str(path), last=val.values[-1] if val.values else None)

    def get_string_set_attribute(
        self, container_id: str, container_type: ContainerType, path: List[str]
    ) -> StringSetField:
        val = self._get_attribute(container_id, container_type, path, StringSet)
        return StringSetField(path=path_to_str(path), values=set(val.values))

    def _get_attribute(
        self,
        container_id: str,
        container_type: ContainerType,
        path: List[str],
        expected_type: Type[Val],
    ) -> Val:
        run = self._get_container(container_id, container_type)
        value: Optional[Value] = run.get(path)
        str_path = path_to_str(path)
        if value is None:
            raise MetadataInconsistency("Attribute {} not found".format(str_path))
        if isinstance(value, expected_type):
            return value
        raise MetadataInconsistency("Attribute {} is not {}".format(str_path, type.__name__))

    def get_string_series_values(
        self,
        container_id: str,
        container_type: ContainerType,
        path: List[str],
        limit: int,
        from_step: Optional[float] = None,
    ) -> StringSeriesValues:
        val = self._get_attribute(container_id, container_type, path, StringSeries)
        return StringSeriesValues(
            len(val.values),
            [StringPointValue(timestamp=datetime.now(), step=idx, value=v) for idx, v in enumerate(val.values)],
        )

    def get_float_series_values(
        self,
        container_id: str,
        container_type: ContainerType,
        path: List[str],
        limit: int,
        from_step: Optional[float] = None,
        use_proto: Optional[bool] = None,
    ) -> FloatSeriesValues:
        val = self._get_attribute(container_id, container_type, path, FloatSeries)
        return FloatSeriesValues(
            len(val.values),
            [FloatPointValue(timestamp=datetime.now(), step=idx, value=v) for idx, v in enumerate(val.values)],
        )

    def get_fields_definitions(
        self,
        container_id: str,
        container_type: ContainerType,
        use_proto: Optional[bool] = None,
    ) -> List[FieldDefinition]:
        return []

    def _get_attribute_values(self, value_dict, path_prefix: List[str]):
        assert isinstance(value_dict, dict)
        for k, value in value_dict.items():
            if isinstance(value, dict):
                yield from self._get_attribute_values(value, path_prefix + [k])
            else:
                attr_type = value.accept(self._attribute_type_converter_value_visitor).value
                attr_path = "/".join(path_prefix + [k])
                if hasattr(value, "value"):
                    yield attr_path, attr_type, value.value
                else:
                    return attr_path, attr_type, NoValue

    def fetch_atom_attribute_values(
        self, container_id: str, container_type: ContainerType, path: List[str]
    ) -> List[Tuple[str, FieldType, Any]]:
        run = self._get_container(container_id, container_type)
        values = self._get_attribute_values(run.get(path), path)
        namespace_prefix = path_to_str(path)
        if namespace_prefix:
            # don't want to catch "ns/attribute/other" while looking for "ns/attr"
            namespace_prefix += "/"
        return [
            (full_path, attr_type, attr_value)
            for (full_path, attr_type, attr_value) in values
            if full_path.startswith(namespace_prefix)
        ]

    def search_leaderboard_entries(
        self,
        project_id: UniqueId,
        types: Optional[Iterable[ContainerType]] = None,
        query: Optional[NQLQuery] = None,
        columns: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
        sort_by: str = "sys/creation_time",
        ascending: bool = False,
        progress_bar: Optional[ProgressBarType] = None,
        use_proto: Optional[bool] = None,
    ) -> Generator[LeaderboardEntry, None, None]:
        """Non relevant for mock"""

    class AttributeTypeConverterValueVisitor(ValueVisitor[FieldType]):
        def visit_float(self, _: Float) -> FieldType:
            return FieldType.FLOAT

        def visit_integer(self, _: Integer) -> FieldType:
            return FieldType.INT

        def visit_boolean(self, _: Boolean) -> FieldType:
            return FieldType.BOOL

        def visit_string(self, _: String) -> FieldType:
            return FieldType.STRING

        def visit_datetime(self, _: Datetime) -> FieldType:
            return FieldType.DATETIME

        def visit_float_series(self, _: FloatSeries) -> FieldType:
            return FieldType.FLOAT_SERIES

        def visit_string_series(self, _: StringSeries) -> FieldType:
            return FieldType.STRING_SERIES

        def visit_string_set(self, _: StringSet) -> FieldType:
            return FieldType.STRING_SET

        def visit_namespace(self, _: Namespace) -> FieldType:
            raise NotImplementedError

        def copy_value(self, source_type: Type[FieldDefinition], source_path: List[str]) -> FieldType:
            raise NotImplementedError

    class NewValueOpVisitor(OperationVisitor[Optional[Value]]):
        def __init__(
            self, backend, path: List[str], current_value: Optional[Value], operation_storage: OperationStorage
        ):
            self._backend = backend
            self._path = path
            self._current_value = current_value
            self._operation_storage = operation_storage

        def visit_assign_float(self, op: AssignFloat) -> Optional[Value]:
            if self._current_value is not None and not isinstance(self._current_value, Float):
                raise self._create_type_error("assign", Float.__name__)
            return Float(op.value)

        def visit_assign_int(self, op: AssignInt) -> Optional[Value]:
            if self._current_value is not None and not isinstance(self._current_value, Integer):
                raise self._create_type_error("assign", Integer.__name__)
            return Integer(op.value)

        def visit_assign_bool(self, op: AssignBool) -> Optional[Value]:
            if self._current_value is not None and not isinstance(self._current_value, Boolean):
                raise self._create_type_error("assign", Boolean.__name__)
            return Boolean(op.value)

        def visit_assign_string(self, op: AssignString) -> Optional[Value]:
            if self._current_value is not None and not isinstance(self._current_value, String):
                raise self._create_type_error("assign", String.__name__)
            return String(op.value)

        def visit_assign_datetime(self, op: AssignDatetime) -> Optional[Value]:
            if self._current_value is not None and not isinstance(self._current_value, Datetime):
                raise self._create_type_error("assign", Datetime.__name__)
            return Datetime(op.value)

        def visit_log_floats(self, op: LogFloats) -> Optional[Value]:
            raw_values = [x.value for x in op.values]
            if self._current_value is None:
                return FloatSeries(raw_values)
            if not isinstance(self._current_value, FloatSeries):
                raise self._create_type_error("log", FloatSeries.__name__)
            return FloatSeries(
                self._current_value.values + raw_values,
                min=self._current_value.min,
                max=self._current_value.max,
                unit=self._current_value.unit,
            )

        def visit_log_strings(self, op: LogStrings) -> Optional[Value]:
            raw_values = [x.value for x in op.values]
            if self._current_value is None:
                return StringSeries(raw_values)
            if not isinstance(self._current_value, StringSeries):
                raise self._create_type_error("log", StringSeries.__name__)
            return StringSeries(self._current_value.values + raw_values)

        def visit_clear_float_log(self, op: ClearFloatLog) -> Optional[Value]:
            if self._current_value is None:
                return FloatSeries([])
            if not isinstance(self._current_value, FloatSeries):
                raise self._create_type_error("clear", FloatSeries.__name__)
            return FloatSeries(
                [],
                min=self._current_value.min,
                max=self._current_value.max,
                unit=self._current_value.unit,
            )

        def visit_clear_string_log(self, op: ClearStringLog) -> Optional[Value]:
            if self._current_value is None:
                return StringSeries([])
            if not isinstance(self._current_value, StringSeries):
                raise self._create_type_error("clear", StringSeries.__name__)
            return StringSeries([])

        def visit_config_float_series(self, op: ConfigFloatSeries) -> Optional[Value]:
            if self._current_value is None:
                return FloatSeries([], min=op.min, max=op.max, unit=op.unit)
            if not isinstance(self._current_value, FloatSeries):
                raise self._create_type_error("log", FloatSeries.__name__)
            return FloatSeries(self._current_value.values, min=op.min, max=op.max, unit=op.unit)

        def visit_add_strings(self, op: AddStrings) -> Optional[Value]:
            if self._current_value is None:
                return StringSet(op.values)
            if not isinstance(self._current_value, StringSet):
                raise self._create_type_error("add", StringSet.__name__)
            return StringSet(self._current_value.values.union(op.values))

        def visit_remove_strings(self, op: RemoveStrings) -> Optional[Value]:
            if self._current_value is None:
                return StringSet(set())
            if not isinstance(self._current_value, StringSet):
                raise self._create_type_error("remove", StringSet.__name__)
            return StringSet(self._current_value.values.difference(op.values))

        def visit_clear_string_set(self, op: ClearStringSet) -> Optional[Value]:
            if self._current_value is None:
                return StringSet(set())
            if not isinstance(self._current_value, StringSet):
                raise self._create_type_error("clear", StringSet.__name__)
            return StringSet(set())

        def visit_delete_attribute(self, op: DeleteAttribute) -> Optional[Value]:
            if self._current_value is None:
                raise MetadataInconsistency(
                    "Cannot perform delete operation on {}. Attribute is undefined.".format(self._path)
                )
            return None

        def visit_copy_attribute(self, op: CopyAttribute) -> Optional[Value]:
            return op.resolve(self._backend).accept(self)

        def _create_type_error(self, op_name, expected):
            return MetadataInconsistency(
                "Cannot perform {} operation on {}. Expected {}, {} found.".format(
                    op_name, self._path, expected, type(self._current_value)
                )
            )

    def get_fields_with_paths_filter(
        self, container_id: str, container_type: ContainerType, paths: List[str], use_proto: Optional[bool] = None
    ) -> List[Field]:
        return []

    def query_fields_definitions_within_project(
        self,
        project_id: QualifiedName,
        field_name_regex: Optional[str] = None,
        experiment_ids_filter: Optional[List[str]] = None,
        next_page: Optional[NextPage] = None,
    ) -> QueryFieldDefinitionsResult:
        return QueryFieldDefinitionsResult(
            entries=[],
            next_page=NextPage(next_page_token=None, limit=0),
        )

    def query_fields_within_project(
        self,
        project_id: QualifiedName,
        field_names_filter: Optional[List[str]] = None,
        experiment_ids_filter: Optional[List[str]] = None,
        next_page: Optional[NextPage] = None,
    ) -> QueryFieldsResult:
        return QueryFieldsResult(
            entries=[],
            next_page=NextPage(next_page_token=None, limit=0),
        )
