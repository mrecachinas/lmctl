"""Cloud client context manager."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientSession
from pylamarzocco import LaMarzoccoCloudClient

from ._constants import USERNAME_ENV_VARS, USERNAME_KEY
from ._credentials import credential, password_credential
from ._keys import load_installation_key


class cloud_client:
    """Async context manager for an authenticated cloud client."""

    def __init__(self, args: Any) -> None:
        self._args = args
        self._session: ClientSession | None = None

    async def __aenter__(self) -> LaMarzoccoCloudClient:
        self._session = ClientSession()
        username = credential(
            self._args.username,
            USERNAME_ENV_VARS,
            "username",
            config_file=self._args.config_file,
            config_key=USERNAME_KEY,
        )
        return LaMarzoccoCloudClient(
            username=username,
            password=password_credential(self._args, username),
            installation_key=load_installation_key(self._args.key_file),
            client=self._session,
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._session is not None:
            await self._session.close()
