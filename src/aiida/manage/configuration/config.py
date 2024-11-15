###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Module that defines the configuration file of an AiiDA instance and functions to create and load it.

Despite the import of the annotations backport below which enables postponed type annotation evaluation as implemented
with PEP 563 (https://peps.python.org/pep-0563/), this is not compatible with ``pydantic`` for Python 3.9 and older (
See https://github.com/pydantic/pydantic/issues/2678 for details).
"""

from __future__ import annotations

import codecs
import contextlib
import io
import json
import os
import warnings
from typing import Any, Dict, Optional

from pydantic import ValidationError

from aiida.common.exceptions import ConfigurationError, EntryPointError, StorageMigrationError
from aiida.common.log import AIIDA_LOGGER
from aiida.common.warnings import AiidaDeprecationWarning

from .options import Option, get_option, get_option_names, parse_option
from .profile import Profile
from .schema import ConfigSchema

__all__ = (
    'get_config',
    'get_config_option',
    'get_config_path',
    'reset_config',
    'CONFIG',
)

LOGGER = AIIDA_LOGGER.getChild('manage.configuration.config')

# global variables for aiida
CONFIG: Optional['Config'] = None


class Config:
    """Object that represents the configuration file of an AiiDA instance."""

    KEY_VERSION = 'CONFIG_VERSION'
    KEY_VERSION_CURRENT = 'CURRENT'
    KEY_VERSION_OLDEST_COMPATIBLE = 'OLDEST_COMPATIBLE'
    KEY_DEFAULT_PROFILE = 'default_profile'
    KEY_PROFILES = 'profiles'
    KEY_OPTIONS = 'options'
    KEY_SCHEMA = '$schema'

    @classmethod
    def from_file(cls, filepath):
        """Instantiate a configuration object from the contents of a given file.

        .. note:: if the filepath does not exist an empty file will be created with the current default configuration
            and will be written to disk. If the filepath does already exist but contains a configuration with an
            outdated schema, the content will be migrated and then written to disk.

        :param filepath: the absolute path to the configuration file
        :return: `Config` instance
        """
        from aiida.cmdline.utils import echo

        from .migrations import check_and_migrate_config, config_needs_migrating

        try:
            with open(filepath, 'rb') as handle:
                config = json.load(handle)
        except FileNotFoundError:
            config = Config(filepath, check_and_migrate_config({}))
            config.store()
        else:
            migrated = False

            # If the configuration file needs to be migrated first create a specific backup so it can easily be reverted
            if config_needs_migrating(config, filepath):
                migrated = True
                echo.echo_warning(f'current configuration file `{filepath}` is outdated and will be migrated')
                filepath_backup = cls._backup(filepath)
                echo.echo_warning(f'original backed up to `{filepath_backup}`')

            config = Config(filepath, check_and_migrate_config(config))

            if migrated:
                config.store()

        return config

    @classmethod
    def _backup(cls, filepath):
        """Create a backup of the configuration file with the given filepath.

        :param filepath: absolute path to the configuration file to backup
        :return: the absolute path of the created backup
        """
        import shutil

        from aiida.common import timezone

        filepath_backup = None

        # Keep generating a new backup filename based on the current time until it does not exist
        while not filepath_backup or os.path.isfile(filepath_backup):
            filepath_backup = f"{filepath}.{timezone.now().strftime('%Y%m%d-%H%M%S.%f')}"

        shutil.copy(filepath, filepath_backup)

        return filepath_backup

    @staticmethod
    def validate(config: dict, filepath: Optional[str] = None):
        """Validate a configuration dictionary."""
        try:
            ConfigSchema(**config)
        except ValidationError as exception:
            raise ConfigurationError(f'invalid config schema: {filepath}: {exception!s}')

    def __init__(self, filepath: str, config: dict, validate: bool = True):
        """Instantiate a configuration object from a configuration dictionary and its filepath.

        If an empty dictionary is passed, the constructor will create the skeleton configuration dictionary.

        :param filepath: the absolute filepath of the configuration file
        :param config: the content of the configuration file in dictionary form
        :param validate: validate the dictionary against the schema
        """
        from .migrations import CURRENT_CONFIG_VERSION, OLDEST_COMPATIBLE_CONFIG_VERSION

        if validate:
            self.validate(config, filepath)

        self._filepath = filepath
        self._schema = config.get(self.KEY_SCHEMA, None)
        version = config.get(self.KEY_VERSION, {})
        self._current_version = version.get(self.KEY_VERSION_CURRENT, CURRENT_CONFIG_VERSION)
        self._oldest_compatible_version = version.get(
            self.KEY_VERSION_OLDEST_COMPATIBLE, OLDEST_COMPATIBLE_CONFIG_VERSION
        )
        self._profiles = {}

        known_keys = [self.KEY_SCHEMA, self.KEY_VERSION, self.KEY_PROFILES, self.KEY_OPTIONS, self.KEY_DEFAULT_PROFILE]
        unknown_keys = set(config.keys()) - set(known_keys)

        if unknown_keys:
            keys = ', '.join(unknown_keys)
            self.handle_invalid(f'encountered unknown keys [{keys}] in `{filepath}` which have been removed')

        try:
            self._options = config[self.KEY_OPTIONS]
        except KeyError:
            self._options = {}

        try:
            self._default_profile = config[self.KEY_DEFAULT_PROFILE]
        except KeyError:
            self._default_profile = None

        for name, config_profile in config.get(self.KEY_PROFILES, {}).items():
            self._profiles[name] = Profile(name, config_profile)

    def __eq__(self, other):
        """Two configurations are considered equal, when their dictionaries are equal."""
        return self.dictionary == other.dictionary

    def __ne__(self, other):
        """Two configurations are considered unequal, when their dictionaries are unequal."""
        return self.dictionary != other.dictionary

    def handle_invalid(self, message):
        """Handle an incoming invalid configuration dictionary.

        The current content of the configuration file will be written to a backup file.

        :param message: a string message to echo with describing the infraction
        """
        from aiida.cmdline.utils import echo

        filepath_backup = self._backup(self.filepath)
        echo.echo_warning(message)
        echo.echo_warning(f'backup of the original config file written to: `{filepath_backup}`')

    @property
    def dictionary(self) -> dict:
        """Return the dictionary representation of the config as it would be written to file.

        :return: dictionary representation of config as it should be written to file
        """
        config = {}
        if self._schema:
            config[self.KEY_SCHEMA] = self._schema

        config[self.KEY_VERSION] = self.version_settings
        config[self.KEY_PROFILES] = {name: profile.dictionary for name, profile in self._profiles.items()}

        if self._default_profile:
            config[self.KEY_DEFAULT_PROFILE] = self._default_profile

        if self._options:
            config[self.KEY_OPTIONS] = self._options

        return config

    @property
    def version(self):
        return self._current_version

    @version.setter
    def version(self, version):
        self._current_version = version

    @property
    def version_oldest_compatible(self):
        return self._oldest_compatible_version

    @version_oldest_compatible.setter
    def version_oldest_compatible(self, version_oldest_compatible):
        self._oldest_compatible_version = version_oldest_compatible

    @property
    def version_settings(self):
        return {
            self.KEY_VERSION_CURRENT: self.version,
            self.KEY_VERSION_OLDEST_COMPATIBLE: self.version_oldest_compatible,
        }

    @property
    def filepath(self):
        return self._filepath

    @property
    def dirpath(self):
        return os.path.dirname(self.filepath)

    @property
    def default_profile_name(self):
        """Return the default profile name.

        :return: the default profile name or None if not defined
        """
        return self._default_profile

    @property
    def profile_names(self):
        """Return the list of profile names.

        :return: list of profile names
        """
        return list(self._profiles.keys())

    @property
    def profiles(self):
        """Return the list of profiles.

        :return: the profiles
        :rtype: list of `Profile` instances
        """
        return list(self._profiles.values())

    def validate_profile(self, name):
        """Validate that a profile exists.

        :param name: name of the profile:
        :raises aiida.common.ProfileConfigurationError: if the name is not found in the configuration file
        """
        from aiida.common import exceptions

        if name not in self.profile_names:
            raise exceptions.ProfileConfigurationError(f'profile `{name}` does not exist')

    def get_profile(self, name: Optional[str] = None) -> Profile:
        """Return the profile for the given name or the default one if not specified.

        :return: the profile instance or None if it does not exist
        :raises aiida.common.ProfileConfigurationError: if the name is not found in the configuration file
        """
        from aiida.common import exceptions

        if not name and not self.default_profile_name:
            raise exceptions.ProfileConfigurationError(
                f'no default profile defined: {self._default_profile}\n{self.dictionary}'
            )

        if not name:
            name = self.default_profile_name

        self.validate_profile(name)

        return self._profiles[name]

    def create_profile(
        self,
        name: str,
        storage_backend: str,
        storage_config: dict[str, Any],
        broker_backend: str | None = None,
        broker_config: dict[str, Any] | None = None,
        is_test_profile: bool = False,
    ) -> Profile:
        """Create a new profile and initialise its storage.

        :param name: The profile name.
        :param storage_backend: The entry point to the :class:`aiida.orm.implementation.storage_backend.StorageBackend`
            implementation to use for the storage.
        :param storage_config: The configuration necessary to initialise and connect to the storage backend.
        :param broker_backend: The entry point to the :class:`aiida.brokers.Broker` implementation to use for the
            message broker.
        :param broker_config: The configuration necessary to initialise and connect to the broker.
        :returns: The created profile.
        :raises ValueError: If the profile already exists.
        :raises TypeError: If the ``storage_backend`` is not a subclass of
            :class:`aiida.orm.implementation.storage_backend.StorageBackend`.
        :raises EntryPointError: If the ``storage_backend`` does not have an associated entry point.
        :raises StorageMigrationError: If the storage cannot be initialised.
        """
        from aiida.brokers import Broker
        from aiida.orm.implementation.storage_backend import StorageBackend
        from aiida.plugins.entry_point import load_entry_point

        if name in self.profile_names:
            raise ValueError(f'The profile `{name}` already exists.')

        try:
            storage_cls = load_entry_point('aiida.storage', storage_backend)
        except EntryPointError as exception:
            raise ValueError(f'The entry point `{storage_backend}` could not be loaded.') from exception
        else:
            if not issubclass(storage_cls, StorageBackend):
                raise TypeError(
                    f'The `storage_backend={storage_backend}` is not a subclass of '
                    '`aiida.orm.implementation.storage_backend.StorageBackend`.'
                )

        storage_config = storage_cls.Model(**(storage_config or {})).model_dump()

        if broker_backend is not None:
            try:
                broker_cls = load_entry_point('aiida.brokers', broker_backend)
            except EntryPointError as exception:
                raise ValueError(f'The entry point `{broker_backend}` could not be loaded.') from exception
            else:
                if not issubclass(broker_cls, Broker):
                    raise TypeError(
                        f'The `broker_backend={broker_backend}` is not a subclass of `aiida.brokers.broker.Broker`.'
                    )

        profile = Profile(
            name,
            {
                'storage': {
                    'backend': storage_backend,
                    'config': storage_config,
                },
                'process_control': {
                    'backend': broker_backend,
                    'config': broker_config,
                },
                'test_profile': is_test_profile,
            },
        )

        LOGGER.report('Initialising the storage backend.')
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                profile.storage_cls.initialise(profile)
        except Exception as exception:
            raise StorageMigrationError(
                f'Storage backend initialisation failed, probably because the configuration is incorrect:\n{exception}'
            )
        LOGGER.report('Storage initialisation completed.')

        self.add_profile(profile)
        self.store()

        return profile

    def add_profile(self, profile):
        """Add a profile to the configuration.

        :param profile: the profile configuration dictionary
        :return: self
        """
        self._profiles[profile.name] = profile
        return self

    def update_profile(self, profile):
        """Update a profile in the configuration.

        :param profile: the profile instance to update
        :return: self
        """
        self._profiles[profile.name] = profile
        return self

    def remove_profile(self, name):
        """Remove a profile from the configuration.

        :param name: the name of the profile to remove
        :raises aiida.common.ProfileConfigurationError: if the given profile does not exist
        :return: self
        """
        self.validate_profile(name)
        self._profiles.pop(name)
        return self

    def delete_profile(self, name: str, delete_storage: bool = True) -> None:
        """Delete a profile including its storage.

        :param delete_storage: Whether to delete the storage with all its data or not.
        """
        from aiida.plugins import StorageFactory

        profile = self.get_profile(name)
        is_default_profile: bool = profile.name == self.default_profile_name

        if delete_storage:
            storage_cls = StorageFactory(profile.storage_backend)
            storage = storage_cls(profile)
            storage.delete()
            LOGGER.report(f'Data storage deleted, configuration was: {profile.storage_config}')
        else:
            LOGGER.report(f'Data storage not deleted, configuration is: {profile.storage_config}')

        self.remove_profile(name)

        if is_default_profile and not self.profile_names:
            LOGGER.warning(f'`{name}` was the default profile, no profiles remain to set as default.')
            self.store()
            return

        if is_default_profile:
            LOGGER.warning(f'`{name}` was the default profile, setting `{self.profile_names[0]}` as the new default.')
            self.set_default_profile(self.profile_names[0], overwrite=True)

        self.store()

    def set_default_profile(self, name, overwrite=False):
        """Set the given profile as the new default.

        :param name: name of the profile to set as new default
        :param overwrite: when True, set the profile as the new default even if a default profile is already defined
        :raises aiida.common.ProfileConfigurationError: if the given profile does not exist
        :return: self
        """
        if self.default_profile_name and not overwrite:
            return self

        self.validate_profile(name)
        self._default_profile = name
        return self

    def set_default_user_email(self, profile: Profile, user_email: str) -> None:
        """Set the default user for the given profile.

        .. warning::

            This does not update the cached default user on the storage backend associated with the profile. To do so,
            use :meth:`aiida.manage.manager.Manager.set_default_user_email` instead.

        :param profile: The profile to update.
        :param user_email: The email of the user to set as the default user.
        """
        profile.default_user_email = user_email
        self.update_profile(profile)
        self.store()

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, value):
        self._options = value

    def set_option(self, option_name, option_value, scope=None, override=True):
        """Set a configuration option for a certain scope.

        :param option_name: the name of the configuration option
        :param option_value: the option value
        :param scope: set the option for this profile or globally if not specified
        :param override: boolean, if False, will not override the option if it already exists

        :returns: the parsed value (potentially cast to a valid type)
        """
        option, parsed_value = parse_option(option_name, option_value)

        if parsed_value is not None:
            value = parsed_value
        elif option.default is not None:
            value = option.default
        else:
            return

        if not option.global_only and scope is not None:
            self.get_profile(scope).set_option(option.name, value, override=override)
        elif option.name not in self.options or override:
            self.options[option.name] = value

        return value

    def unset_option(self, option_name: str, scope=None):
        """Unset a configuration option for a certain scope.

        :param option_name: the name of the configuration option
        :param scope: unset the option for this profile or globally if not specified
        """
        option = get_option(option_name)

        if scope is not None:
            self.get_profile(scope).unset_option(option.name)
        else:
            self.options.pop(option.name, None)

    def get_option(self, option_name, scope=None, default=True):
        """Get a configuration option for a certain scope.

        :param option_name: the name of the configuration option
        :param scope: get the option for this profile or globally if not specified
        :param default: boolean, If True will return the option default, even if not defined within the given scope
        :return: the option value or None if not set for the given scope
        """
        option = get_option(option_name)
        default_value = option.default if default else None

        if scope is not None:
            value = self.get_profile(scope).get_option(option.name, default_value)
        else:
            value = self.options.get(option.name, default_value)

        return value

    def get_options(self, scope: Optional[str] = None) -> Dict[str, tuple[Option, str, Any]]:
        """Return a dictionary of all option values and their source ('profile', 'global', or 'default').

        :param scope: the profile name or globally if not specified
        :returns: (option, source, value)
        """
        profile = self.get_profile(scope) if scope else None
        output = {}
        for name in get_option_names():
            option = get_option(name)
            if profile and name in profile.options:
                value = profile.options.get(name)
                source = 'profile'
            elif name in self.options:
                value = self.options.get(name)
                source = 'global'
            elif option.default is not None:
                value = option.default
                source = 'default'
            else:
                continue
            output[name] = (option, source, value)
        return output

    def store(self):
        """Write the current config to file.

        .. note:: if the configuration file already exists on disk and its contents differ from those in memory, a
            backup of the original file on disk will be created before overwriting it.

        :return: self
        """
        import tempfile

        from aiida.common.files import md5_file, md5_from_filelike

        from .settings import DEFAULT_CONFIG_INDENT_SIZE

        # If the filepath of this configuration does not yet exist, simply write it.
        if not os.path.isfile(self.filepath):
            self._atomic_write()
            return self

        # Otherwise, we write the content to a temporary file and compare its md5 checksum with the current config on
        # disk. When the checksums differ, we first create a backup and only then overwrite the existing file.
        with tempfile.NamedTemporaryFile() as handle:
            json.dump(self.dictionary, codecs.getwriter('utf-8')(handle), indent=DEFAULT_CONFIG_INDENT_SIZE)
            handle.seek(0)

            if md5_from_filelike(handle) != md5_file(self.filepath):
                self._backup(self.filepath)

        self._atomic_write()

        return self

    def _atomic_write(self, filepath=None):
        """Write the config as it is in memory, i.e. the contents of ``self.dictionary``, to disk.

        .. note:: this command will write the config from memory to a temporary file in the same directory as the
            target file ``filepath``. It will then use ``os.rename`` to move the temporary file to ``filepath`` which
            will be overwritten if it already exists. The ``os.rename`` is the operation that gives the best guarantee
            of being atomic within the limitations of the application.

        :param filepath: optional filepath to write the contents to, if not specified, the default filename is used.
        """
        import tempfile

        from .settings import DEFAULT_CONFIG_INDENT_SIZE, DEFAULT_UMASK

        umask = os.umask(DEFAULT_UMASK)

        if filepath is None:
            filepath = self.filepath

        # Create a temporary file in the same directory as the target filepath, which guarantees that the temporary
        # file is on the same filesystem, which is necessary to be able to use ``os.rename``. Since we are moving the
        # temporary file, we should also tell the tempfile to not be automatically deleted as that will raise.
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(filepath), delete=False, mode='w') as handle:
            try:
                json.dump(self.dictionary, handle, indent=DEFAULT_CONFIG_INDENT_SIZE)
            finally:
                os.umask(umask)

            handle.flush()
            os.rename(handle.name, self.filepath)


def get_config_path():
    """Returns path to .aiida configuration directory."""
    from .settings import AIIDA_CONFIG_FOLDER, DEFAULT_CONFIG_FILE_NAME

    return os.path.join(AIIDA_CONFIG_FOLDER, DEFAULT_CONFIG_FILE_NAME)


def load_config(create=False) -> 'Config':
    """Instantiate Config object representing an AiiDA configuration file.

    Warning: Contrary to :func:`~aiida.manage.configuration.get_config`, this function is uncached and will always
    create a new Config object. You may want to call :func:`~aiida.manage.configuration.get_config` instead.

    :param create: if True, will create the configuration file if it does not already exist
    :type create: bool

    :return: the config
    :rtype: :class:`~aiida.manage.configuration.config.Config`
    :raises aiida.common.MissingConfigurationError: if the configuration file could not be found and create=False
    """
    from aiida.common import exceptions

    from .config import Config

    filepath = get_config_path()

    if not os.path.isfile(filepath) and not create:
        raise exceptions.MissingConfigurationError(f'configuration file {filepath} does not exist')

    try:
        config = Config.from_file(filepath)
    except ValueError as exc:
        raise exceptions.ConfigurationError(f'configuration file {filepath} contains invalid JSON') from exc

    _merge_deprecated_cache_yaml(config, filepath)

    return config


def _merge_deprecated_cache_yaml(config, filepath):
    """Merge the deprecated cache_config.yml into the config."""
    cache_path = os.path.join(os.path.dirname(filepath), 'cache_config.yml')
    if not os.path.exists(cache_path):
        return

    # Imports are here to avoid them when not needed
    import shutil

    import yaml

    from aiida.common import timezone

    cache_path_backup = None
    # Keep generating a new backup filename based on the current time until it does not exist
    while not cache_path_backup or os.path.isfile(cache_path_backup):
        cache_path_backup = f"{cache_path}.{timezone.now().strftime('%Y%m%d-%H%M%S.%f')}"

    warnings.warn(
        'cache_config.yml use is deprecated and support will be removed in `v3.0`. Merging into config.json and '
        f'moving to: {cache_path_backup}',
        AiidaDeprecationWarning,
        stacklevel=2,
    )

    with open(cache_path, 'r', encoding='utf8') as handle:
        cache_config = yaml.safe_load(handle)
    for profile_name, data in cache_config.items():
        if profile_name not in config.profile_names:
            warnings.warn(f"Profile '{profile_name}' from cache_config.yml not in config.json, skipping", UserWarning)
            continue
        for key, option_name in [
            ('default', 'caching.default_enabled'),
            ('enabled', 'caching.enabled_for'),
            ('disabled', 'caching.disabled_for'),
        ]:
            if key in data:
                value = data[key]
                # in case of empty key
                value = [] if value is None and key != 'default' else value
                config.set_option(option_name, value, scope=profile_name)
    config.store()
    shutil.move(cache_path, cache_path_backup)


def reset_config():
    """Reset the globally loaded config.

    .. warning:: This is experimental functionality and should for now be used only internally. If the reset is unclean
        weird unknown side-effects may occur that end up corrupting or destroying data.
    """
    global CONFIG  # noqa: PLW0603
    CONFIG = None


def get_config(create=False):
    """Return the current configuration.

    If the configuration has not been loaded yet
     * the configuration is loaded using ``load_config``
     * the global `CONFIG` variable is set
     * the configuration object is returned

    Note: This function will except if no configuration file can be found. Only call this function, if you need
    information from the configuration file.

    :param create: if True, will create the configuration file if it does not already exist
    :type create: bool

    :return: the config
    :rtype: :class:`~aiida.manage.configuration.config.Config`
    :raises aiida.common.ConfigurationError: if the configuration file could not be found, read or deserialized
    """
    global CONFIG  # noqa: PLW0603

    if not CONFIG:
        CONFIG = load_config(create=create)

        if CONFIG.get_option('warnings.showdeprecations'):
            # If the user does not want to get AiiDA deprecation warnings, we disable them - this can be achieved with::
            #   verdi config warnings.showdeprecations False
            # Note that the AiidaDeprecationWarning does NOT inherit from DeprecationWarning
            warnings.simplefilter('default', AiidaDeprecationWarning)
            # This should default to 'once', i.e. once per different message
        else:
            warnings.simplefilter('ignore', AiidaDeprecationWarning)

    return CONFIG


def get_config_option(option_name: str) -> Any:
    """Return the value of a configuration option.

    In order of priority, the option is returned from:

    1. The current profile, if loaded and the option specified
    2. The current configuration, if loaded and the option specified
    3. The default value for the option

    :param option_name: the name of the option to return
    :return: the value of the option
    :raises `aiida.common.exceptions.ConfigurationError`: if the option is not found
    """
    from aiida.manage import get_manager

    return get_manager().get_option(option_name)
