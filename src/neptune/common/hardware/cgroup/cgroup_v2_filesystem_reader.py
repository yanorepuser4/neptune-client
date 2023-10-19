#
# Copyright (c) 2019, Neptune Labs Sp. z o.o.
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
import os
import re
from typing import (
    Optional,
    Tuple,
    Union,
)

from neptune.common.hardware.cgroup.cgroup_filesystem_reader import CGroupAbstractFilesystemReader


class CGroupV2FilesystemReader(CGroupAbstractFilesystemReader):
    def __init__(self) -> None:
        cgroup_dir = self.__cgroup_mount_dir()
        assert cgroup_dir is not None, "Mount directory cgroup2 not found"
        self.__memory_usage_file = os.path.join(cgroup_dir, "memory.current")
        self.__memory_limit_file = os.path.join(cgroup_dir, "memory.max")
        self.__cpu_max_file = os.path.join(cgroup_dir, "cpu.max")
        self.__cpu_stat_file = os.path.join(cgroup_dir, "cpu.stat")

    def get_memory_usage_in_bytes(self) -> int:
        return self.__read_int_file(self.__memory_usage_file)

    def get_memory_limit_in_bytes(self) -> int:
        return self.__read_int_file(self.__memory_limit_file)

    def get_cpu_max_limits(self) -> Tuple[Union[str, int], int]:
        return self.__read_two_values_from_first_line(self.__cpu_max_file)

    def get_cpuacct_usage_nanos(self) -> int:
        return self.__read_int_attr_in_file(self.__cpu_stat_file, "usage_usec") * 1000

    def __read_two_values_from_first_line(self, filename: str) -> Tuple[Union[str, int], int]:
        with open(filename) as f:
            line = f.readline()
            cpu_quota_micros, cpu_period_micros = line.split()
            return cpu_quota_micros, int(cpu_period_micros)

    def __read_int_file(self, filename: str) -> int:
        with open(filename) as f:
            return int(f.read())

    def __read_int_attr_in_file(self, filename: str, attribute: str) -> int:
        with open(filename) as f:
            for line in f.readlines():
                attr, value = line.split()
                if attr == attribute:
                    return int(value)
            raise ValueError(f"Attribute {attribute} not found in {filename}.")

    @staticmethod
    def __cgroup_mount_dir() -> Optional[str]:
        with open("/proc/mounts", "r") as f:
            for line in f.readlines():
                split_line = re.split(r"\s+", line)
                type_ = split_line[2]
                mount_dir = split_line[1]

                if type_ == "cgroup2":
                    assert "cgroup" in mount_dir
                    return mount_dir

        return None

    @staticmethod
    def cgroupv2_is_supported() -> bool:
        if CGroupV2FilesystemReader.__cgroup_mount_dir() is None:
            return False
        else:
            return True