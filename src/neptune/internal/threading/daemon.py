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
__all__ = ["Daemon"]

import abc
import functools
import threading
import time
from enum import Enum

from neptune.common.exceptions import NeptuneConnectionLostException
from neptune.internal.utils.logger import logger


class Daemon(threading.Thread):
    class DaemonState(Enum):
        INIT = 1
        RUNNING = 2
        PAUSED = 3
        INTERRUPTED = 4
        STOPPED = 5

    def __init__(self, sleep_time: float, name):
        super().__init__(daemon=True, name=name)
        self._sleep_time = sleep_time
        self._state: Daemon.DaemonState = Daemon.DaemonState.INIT
        self._wait_condition = threading.Condition()
        self._state_change_notice_condition = threading.Condition()
        self.last_backoff_time = 0  # used only with ConnectionRetryWrapper decorator

    def interrupt(self):
        with self._state_change_notice_condition:
            self._state = Daemon.DaemonState.INTERRUPTED
            self.wake_up()

    def pause(self):
        with self._state_change_notice_condition:
            self._state = Daemon.DaemonState.PAUSED
            self.wake_up()
            self._state_change_notice_condition.wait()

    def resume(self):
        with self._state_change_notice_condition:
            self._state = Daemon.DaemonState.RUNNING
            self.wake_up()

    def wake_up(self):
        with self._wait_condition:
            self._wait_condition.notify_all()

    def disable_sleep(self):
        self._sleep_time = 0

    def is_running(self) -> bool:
        return self._state == Daemon.DaemonState.RUNNING

    def _is_interrupted(self) -> bool:
        return self._state == Daemon.DaemonState.INTERRUPTED

    def run(self):
        self._state = Daemon.DaemonState.RUNNING
        try:
            while not self._is_interrupted():
                start_state = self._state
                with self._state_change_notice_condition:
                    self._state_change_notice_condition.notify_all()

                if self._state == Daemon.DaemonState.PAUSED:
                    pass
                if self._state == Daemon.DaemonState.INTERRUPTED:
                    pass
                if self._state == Daemon.DaemonState.RUNNING:
                    self.work()

                if self._sleep_time > 0 and not self._is_interrupted():
                    with self._wait_condition:
                        if self._state == start_state:
                            self._wait_condition.wait(timeout=self._sleep_time)
        finally:
            self._state = Daemon.DaemonState.STOPPED

    @abc.abstractmethod
    def work(self):
        pass

    class ConnectionRetryWrapper:
        INITIAL_RETRY_BACKOFF = 2
        MAX_RETRY_BACKOFF = 120

        def __init__(self, kill_message):
            self.kill_message = kill_message

        def __call__(self, func):
            @functools.wraps(func)
            def wrapper(self_: Daemon, *args, **kwargs):
                while not self_._is_interrupted():
                    try:
                        result = func(self_, *args, **kwargs)
                        if self_.last_backoff_time > 0:
                            self_.last_backoff_time = 0
                            logger.info("Communication with Neptune restored!")
                        return result
                    except NeptuneConnectionLostException as e:
                        if self_.last_backoff_time == 0:
                            logger.warning(
                                "Experiencing connection interruptions."
                                " Will try to reestablish communication with Neptune."
                                " Internal exception was: %s",
                                e.cause.__class__.__name__,
                            )
                            self_.last_backoff_time = self.INITIAL_RETRY_BACKOFF
                        else:
                            self_.last_backoff_time = min(self_.last_backoff_time * 2, self.MAX_RETRY_BACKOFF)
                        time.sleep(self_.last_backoff_time)
                    except Exception:
                        logger.error(
                            "Unexpected error occurred in Neptune background thread: %s",
                            self.kill_message,
                        )
                        raise

            return wrapper
