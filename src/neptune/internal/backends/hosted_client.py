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
__all__ = [
    "DEFAULT_REQUEST_KWARGS",
    "DEFAULT_PROTO_REQUEST_KWARGS",
    "create_http_client_with_auth",
    "create_backend_client",
    "create_leaderboard_client",
]

import os
import platform
from typing import (
    Dict,
    Tuple,
)

import requests
from bravado.http_client import HttpClient
from bravado.requests_client import RequestsClient
from packaging.version import parse

from neptune.envs import NEPTUNE_REQUEST_TIMEOUT
from neptune.exceptions import NeptuneClientUpgradeRequiredError
from neptune.internal.backends.api_model import ClientConfig
from neptune.internal.backends.swagger_client_wrapper import SwaggerClientWrapper
from neptune.internal.backends.utils import (
    NeptuneResponseAdapter,
    build_operation_url,
    cache,
    create_swagger_client,
    update_session_proxies,
    verify_client_version,
    verify_host_resolution,
    with_api_exceptions_handler,
)
from neptune.internal.credentials import Credentials
from neptune.internal.oauth import NeptuneAuthenticator
from neptune.version import __version__

BACKEND_SWAGGER_PATH = "/api/backend/swagger.json"
LEADERBOARD_SWAGGER_PATH = "/api/leaderboard/swagger.json"

CONNECT_TIMEOUT = 30  # helps detecting internet connection lost
REQUEST_TIMEOUT = int(os.getenv(NEPTUNE_REQUEST_TIMEOUT, "600"))

DEFAULT_REQUEST_KWARGS = {
    "_request_options": {
        "connect_timeout": CONNECT_TIMEOUT,
        "timeout": REQUEST_TIMEOUT,
        "headers": {},
    }
}

DEFAULT_PROTO_REQUEST_KWARGS = {
    "_request_options": {
        **DEFAULT_REQUEST_KWARGS["_request_options"],
        "headers": {
            **DEFAULT_REQUEST_KWARGS["_request_options"]["headers"],
            "Accept": "application/x-protobuf,application/json",
            "Accept-Encoding": "gzip, deflate, br",
        },
    }
}


def _close_connections_on_fork(session: requests.Session):
    try:
        os.register_at_fork(before=session.close, after_in_child=session.close, after_in_parent=session.close)
    except AttributeError:
        pass


# WARNING: Be careful when changing this function. It is used in the experimental package
def _set_pool_size(http_client: RequestsClient) -> None:
    _ = http_client


def create_http_client(ssl_verify: bool, proxies: Dict[str, str]) -> RequestsClient:
    http_client = RequestsClient(ssl_verify=ssl_verify, response_adapter_class=NeptuneResponseAdapter)
    http_client.session.verify = ssl_verify

    _set_pool_size(http_client)

    _close_connections_on_fork(http_client.session)

    update_session_proxies(http_client.session, proxies)

    user_agent = "neptune-client/{lib_version} ({system}, python {python_version})".format(
        lib_version=__version__,
        system=platform.platform(),
        python_version=platform.python_version(),
    )
    http_client.session.headers.update({"User-Agent": user_agent})

    return http_client


@cache
def _get_token_client(
    credentials: Credentials,
    ssl_verify: bool,
    proxies: Dict[str, str],
    endpoint_url: str = None,
) -> SwaggerClientWrapper:
    config_api_url = credentials.api_url_opt or credentials.token_origin_address
    if proxies is None:
        verify_host_resolution(config_api_url)

    token_http_client = create_http_client(ssl_verify, proxies)

    return SwaggerClientWrapper(
        create_swagger_client(
            build_operation_url(endpoint_url or config_api_url, BACKEND_SWAGGER_PATH),
            token_http_client,
        )
    )


@cache
@with_api_exceptions_handler
def get_client_config(credentials: Credentials, ssl_verify: bool, proxies: Dict[str, str]) -> ClientConfig:
    backend_client = _get_token_client(credentials=credentials, ssl_verify=ssl_verify, proxies=proxies)

    config = backend_client.api.getClientConfig(**DEFAULT_REQUEST_KWARGS).response().result

    neptune_version = parse(__version__)
    client_config = ClientConfig.from_api_response(config)
    if not client_config.version_info:
        raise NeptuneClientUpgradeRequiredError(neptune_version, max_version="0.4.111")
    return client_config


@cache
def create_http_client_with_auth(
    credentials: Credentials, ssl_verify: bool, proxies: Dict[str, str]
) -> Tuple[RequestsClient, ClientConfig]:
    client_config = get_client_config(credentials=credentials, ssl_verify=ssl_verify, proxies=proxies)

    config_api_url = credentials.api_url_opt or credentials.token_origin_address

    neptune_version = parse(__version__)
    verify_client_version(client_config, neptune_version)

    endpoint_url = None
    if config_api_url != client_config.api_url:
        endpoint_url = build_operation_url(client_config.api_url, BACKEND_SWAGGER_PATH)

    http_client = create_http_client(ssl_verify=ssl_verify, proxies=proxies)
    http_client.authenticator = NeptuneAuthenticator(
        credentials.api_token,
        _get_token_client(
            credentials=credentials,
            ssl_verify=ssl_verify,
            proxies=proxies,
            endpoint_url=endpoint_url,
        ),
        ssl_verify,
        proxies,
    )

    return http_client, client_config


@cache
def create_backend_client(client_config: ClientConfig, http_client: HttpClient) -> SwaggerClientWrapper:
    return SwaggerClientWrapper(
        create_swagger_client(
            build_operation_url(client_config.api_url, BACKEND_SWAGGER_PATH),
            http_client,
        )
    )


@cache
def create_leaderboard_client(client_config: ClientConfig, http_client: HttpClient) -> SwaggerClientWrapper:
    return SwaggerClientWrapper(
        create_swagger_client(
            build_operation_url(client_config.api_url, LEADERBOARD_SWAGGER_PATH),
            http_client,
        )
    )
