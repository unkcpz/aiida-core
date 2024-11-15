###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""AiiDA profile related code"""

from __future__ import annotations

import collections
import os
import pathlib
from contextlib import contextmanager
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Type

from aiida.common import exceptions

from .options import parse_option

if TYPE_CHECKING:
    from aiida.orm import User
    from aiida.orm.implementation import StorageBackend

    from .config import Config

__all__ = (
    'Profile',
    'create_profile',
    'get_profile',
    'load_profile',
    'profile_context',
)


class Profile:
    """Class that models a profile as it is stored in the configuration file of an AiiDA instance."""

    KEY_UUID = 'PROFILE_UUID'
    KEY_DEFAULT_USER_EMAIL = 'default_user_email'
    KEY_STORAGE = 'storage'
    KEY_PROCESS = 'process_control'
    KEY_STORAGE_BACKEND = 'backend'
    KEY_STORAGE_CONFIG = 'config'
    KEY_PROCESS_BACKEND = 'backend'
    KEY_PROCESS_CONFIG = 'config'
    KEY_OPTIONS = 'options'
    KEY_TEST_PROFILE = 'test_profile'

    # keys that are expected to be in the parsed configuration
    REQUIRED_KEYS = (
        KEY_STORAGE,
        KEY_PROCESS,
    )

    def __init__(self, name: str, config: Mapping[str, Any], validate=True):
        """Load a profile with the profile configuration."""
        if not isinstance(config, collections.abc.Mapping):
            raise TypeError(f'config should be a mapping but is {type(config)}')
        if validate and not set(config.keys()).issuperset(self.REQUIRED_KEYS):
            raise exceptions.ConfigurationError(
                f'profile {name!r} configuration does not contain all required keys: {self.REQUIRED_KEYS}'
            )

        self._name = name
        self._attributes: Dict[str, Any] = deepcopy(config)

        # Create a default UUID if not specified
        if self._attributes.get(self.KEY_UUID, None) is None:
            from uuid import uuid4

            self._attributes[self.KEY_UUID] = uuid4().hex

    def __repr__(self) -> str:
        return f'Profile<uuid={self.uuid!r} name={self.name!r}>'

    def copy(self):
        """Return a copy of the profile."""
        return self.__class__(self.name, self._attributes)

    @property
    def uuid(self) -> str:
        """Return the profile uuid.

        :return: string UUID
        """
        return self._attributes[self.KEY_UUID]

    @uuid.setter
    def uuid(self, value: str) -> None:
        self._attributes[self.KEY_UUID] = value

    @property
    def default_user_email(self) -> Optional[str]:
        """Return the default user email."""
        return self._attributes.get(self.KEY_DEFAULT_USER_EMAIL, None)

    @default_user_email.setter
    def default_user_email(self, value: Optional[str]) -> None:
        """Set the default user email."""
        self._attributes[self.KEY_DEFAULT_USER_EMAIL] = value

    @property
    def storage_backend(self) -> str:
        """Return the type of the storage backend."""
        return self._attributes[self.KEY_STORAGE][self.KEY_STORAGE_BACKEND]

    @property
    def storage_config(self) -> Dict[str, Any]:
        """Return the configuration required by the storage backend."""
        return self._attributes[self.KEY_STORAGE][self.KEY_STORAGE_CONFIG]

    def set_storage(self, name: str, config: Dict[str, Any]) -> None:
        """Set the storage backend and its configuration.

        :param name: the name of the storage backend
        :param config: the configuration of the storage backend
        """
        self._attributes.setdefault(self.KEY_STORAGE, {})
        self._attributes[self.KEY_STORAGE][self.KEY_STORAGE_BACKEND] = name
        self._attributes[self.KEY_STORAGE][self.KEY_STORAGE_CONFIG] = config

    @property
    def storage_cls(self) -> Type['StorageBackend']:
        """Return the storage backend class for this profile."""
        from aiida.plugins import StorageFactory

        return StorageFactory(self.storage_backend)

    @property
    def process_control_backend(self) -> str | None:
        """Return the type of the process control backend."""
        return self._attributes[self.KEY_PROCESS][self.KEY_PROCESS_BACKEND]

    @property
    def process_control_config(self) -> Dict[str, Any]:
        """Return the configuration required by the process control backend."""
        return self._attributes[self.KEY_PROCESS][self.KEY_PROCESS_CONFIG] or {}

    def set_process_controller(self, name: str, config: Dict[str, Any]) -> None:
        """Set the process control backend and its configuration.

        :param name: the name of the process backend
        :param config: the configuration of the process backend
        """
        self._attributes.setdefault(self.KEY_PROCESS, {})
        self._attributes[self.KEY_PROCESS][self.KEY_PROCESS_BACKEND] = name
        self._attributes[self.KEY_PROCESS][self.KEY_PROCESS_CONFIG] = config

    @property
    def options(self):
        self._attributes.setdefault(self.KEY_OPTIONS, {})
        return self._attributes[self.KEY_OPTIONS]

    @options.setter
    def options(self, value):
        self._attributes[self.KEY_OPTIONS] = value

    def get_option(self, option_key, default=None):
        return self.options.get(option_key, default)

    def set_option(self, option_key, value, override=True):
        """Set a configuration option for a certain scope.

        :param option_key: the key of the configuration option
        :param option_value: the option value
        :param override: boolean, if False, will not override the option if it already exists
        """
        _, parsed_value = parse_option(option_key, value)  # ensure the value is validated
        if option_key not in self.options or override:
            self.options[option_key] = parsed_value

    def unset_option(self, option_key):
        self.options.pop(option_key, None)

    @property
    def name(self):
        """Return the profile name.

        :return: the profile name
        """
        return self._name

    @property
    def dictionary(self) -> Dict[str, Any]:
        """Return the profile attributes as a dictionary with keys as it is stored in the config

        :return: the profile configuration dictionary
        """
        return self._attributes

    @property
    def is_test_profile(self) -> bool:
        """Return whether the profile is a test profile

        :return: boolean, True if test profile, False otherwise
        """
        # Check explicitly for ``True`` for safety. If an invalid value is defined, we default to treating it as not
        # a test profile as that can unintentionally clear the database.
        return self._attributes.get(self.KEY_TEST_PROFILE, False) is True

    @is_test_profile.setter
    def is_test_profile(self, value: bool) -> None:
        """Set whether the profile is a test profile.

        :param value: boolean indicating whether this profile is a test profile.
        """
        self._attributes[self.KEY_TEST_PROFILE] = value

    @property
    def repository_path(self) -> pathlib.Path:
        """Return the absolute path of the repository configured for this profile.

        The URI should be in the format `protocol://address`

        :note: At the moment, only the file protocol is supported.

        :return: absolute filepath of the profile's file repository
        """
        from urllib.parse import urlparse

        from aiida.common.warnings import warn_deprecation

        warn_deprecation('This method has been deprecated', version=3)

        if 'repository_uri' not in self.storage_config:
            raise KeyError('repository_uri not defined in profile storage config')

        parts = urlparse(self.storage_config['repository_uri'])

        if parts.scheme != 'file':
            raise exceptions.ConfigurationError('invalid repository protocol, only the local `file://` is supported')

        if not os.path.isabs(parts.path):
            raise exceptions.ConfigurationError('invalid repository URI: the path has to be absolute')

        return pathlib.Path(os.path.expanduser(parts.path))

    @property
    def filepaths(self):
        """Return the filepaths used by this profile.

        :return: a dictionary of filepaths
        """
        from .settings import DAEMON_DIR, DAEMON_LOG_DIR

        return {
            'circus': {
                'log': str(DAEMON_LOG_DIR / f'circus-{self.name}.log'),
                'pid': str(DAEMON_DIR / f'circus-{self.name}.pid'),
                'port': str(DAEMON_DIR / f'circus-{self.name}.port'),
                'socket': {
                    'file': str(DAEMON_DIR / f'circus-{self.name}.sockets'),
                    'controller': 'circus.c.sock',
                    'pubsub': 'circus.p.sock',
                    'stats': 'circus.s.sock',
                },
            },
            'daemon': {
                'log': str(DAEMON_LOG_DIR / f'aiida-{self.name}.log'),
                'pid': str(DAEMON_DIR / f'aiida-{self.name}.pid'),
            },
        }


def create_default_user(
    profile: Profile,
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    institution: Optional[str] = None,
) -> User:
    """Create a default user for the given profile.

    If the profile's storage is read only, a random existing user will be queried and set as default. Otherwise a new
    user is created with the provided details and set as user.

    :param profile: The profile to create the user in.
    :param email: Email for the default user.
    :param first_name: First name for the default user.
    :param last_name: Last name for the default user.
    :param institution: Institution for the default user.
    :returns: The user that was set as the default user.
    """
    from aiida.manage import get_manager
    from aiida.orm import User

    with profile_context(profile, allow_switch=True):
        manager = get_manager()
        storage = manager.get_profile_storage()

        if storage.read_only:
            # Check if the storage contains any users, and just set a random one as default user.
            user = User.collection.query().first(flat=True)
        else:
            # Otherwise create a user and store it
            user = User(email=email, first_name=first_name, last_name=last_name, institution=institution).store()

        # The user can be ``None`` if the storage is read-only and doesn't contain any users. This shouldn't happen in
        # real situations, but this safe guard is added to be safe.
        if user:
            manager.set_default_user_email(profile, user.email)

    return user


def create_profile(
    config: 'Config',
    *,
    storage_backend: str,
    storage_config: dict[str, Any],
    broker_backend: str | None = None,
    broker_config: dict[str, Any] | None = None,
    name: str,
    email: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    institution: Optional[str] = None,
    is_test_profile: bool = False,
) -> Profile:
    """Create a new profile, initialise its storage and create a default user.

    :param config: The config instance.
    :param name: Name of the profile.
    :param email: Email for the default user.
    :param first_name: First name for the default user.
    :param last_name: Last name for the default user.
    :param institution: Institution for the default user.
    :param create_user: If `True`, creates a user that is set as the default user.
    :param storage_backend: The entry point to the :class:`aiida.orm.implementation.storage_backend.StorageBackend`
        implementation to use for the storage.
    :param storage_config: The configuration necessary to initialise and connect to the storage backend.
    :param broker_backend: The entry point to the :class:`aiida.brokers.Broker` implementation to use for the broker.
    :param broker_config: The configuration necessary to initialise and connect to the broker.
    """
    profile: Profile = config.create_profile(
        name=name,
        storage_backend=storage_backend,
        storage_config=storage_config,
        broker_backend=broker_backend,
        broker_config=broker_config,
        is_test_profile=is_test_profile,
    )

    create_default_user(profile, email, first_name, last_name, institution)

    return profile


def load_profile(profile: Optional[str] = None, allow_switch=False) -> 'Profile':
    """Load a global profile, unloading any previously loaded profile.

    .. note:: if a profile is already loaded and no explicit profile is specified, nothing will be done

    :param profile: the name of the profile to load, by default will use the one marked as default in the config
    :param allow_switch: if True, will allow switching to a different profile when storage is already loaded

    :return: the loaded `Profile` instance
    :raises `aiida.common.exceptions.InvalidOperation`:
        if another profile has already been loaded and allow_switch is False
    """
    from aiida.manage import get_manager

    return get_manager().load_profile(profile, allow_switch)


def get_profile() -> Optional['Profile']:
    """Return the currently loaded profile.

    :return: the globally loaded `Profile` instance or `None`
    """
    from aiida.manage import get_manager

    return get_manager().get_profile()


@contextmanager
def profile_context(profile: 'Profile' | str | None = None, allow_switch=False) -> 'Profile':
    """Return a context manager for temporarily loading a profile, and unloading on exit.

    :param profile: the name of the profile to load, by default will use the one marked as default in the config
    :param allow_switch: if True, will allow switching to a different profile

    :return: a context manager for temporarily loading a profile
    """
    from aiida.manage import get_manager

    manager = get_manager()
    current_profile = manager.get_profile()
    yield manager.load_profile(profile, allow_switch)
    if current_profile is None:
        manager.unload_profile()
    else:
        manager.load_profile(current_profile, allow_switch=True)
