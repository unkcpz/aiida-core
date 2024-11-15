###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from aiida.common.log import LogLevels

if TYPE_CHECKING:
    from uuid import UUID


class ConfigVersionSchema(BaseModel, defer_build=True):
    """Schema for the version configuration of an AiiDA instance."""

    CURRENT: int
    OLDEST_COMPATIBLE: int


class ProfileOptionsSchema(BaseModel, defer_build=True):
    """Schema for the options of an AiiDA profile."""

    model_config = ConfigDict(use_enum_values=True)

    runner__poll__interval: int = Field(60, description='Polling interval in seconds to be used by process runners.')
    daemon__default_workers: int = Field(
        1, description='Default number of workers to be launched by `verdi daemon start`.'
    )
    daemon__timeout: int = Field(
        2,
        description='Used to set default timeout in the `DaemonClient` for calls to the daemon.',
    )
    daemon__worker_process_slots: int = Field(
        200, description='Maximum number of concurrent process tasks that each daemon worker can handle.'
    )
    daemon__recursion_limit: int = Field(3000, description='Maximum recursion depth for the daemon workers.')
    db__batch_size: int = Field(
        100000,
        description='Batch size for bulk CREATE operations in the database. Avoids hitting MaxAllocSize of PostgreSQL '
        '(1GB) when creating large numbers of database records in one go.',
    )
    verdi__shell__auto_import: str = Field(
        ':',
        description='Additional modules/functions/classes to be automatically loaded in `verdi shell`, split by `:`.',
    )
    logging__aiida_loglevel: LogLevels = Field(
        'REPORT', description='Minimum level to log to daemon log and the `DbLog` table for the `aiida` logger.'
    )
    logging__verdi_loglevel: LogLevels = Field(
        'REPORT', description='Minimum level to log to console when running a `verdi` command.'
    )
    logging__disk_objectstore_loglevel: LogLevels = Field(
        'INFO', description='Minimum level to log to daemon log and the `DbLog` table for `disk_objectstore` logger.'
    )
    logging__db_loglevel: LogLevels = Field('REPORT', description='Minimum level to log to the DbLog table.')
    logging__plumpy_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `plumpy` logger.'
    )
    logging__kiwipy_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `kiwipy` logger'
    )
    logging__paramiko_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `paramiko` logger'
    )
    logging__alembic_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `alembic` logger'
    )
    logging__sqlalchemy_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `sqlalchemy` logger'
    )
    logging__circus_loglevel: LogLevels = Field(
        'INFO', description='Minimum level to log to daemon log and the `DbLog` table for the `circus` logger'
    )
    logging__aiopika_loglevel: LogLevels = Field(
        'WARNING', description='Minimum level to log to daemon log and the `DbLog` table for the `aiopika` logger'
    )
    warnings__showdeprecations: bool = Field(True, description='Whether to print AiiDA deprecation warnings.')
    warnings__rabbitmq_version: bool = Field(
        True, description='Whether to print a warning when an incompatible version of RabbitMQ is configured.'
    )
    transport__task_retry_initial_interval: int = Field(
        20, description='Initial time interval for the exponential backoff mechanism.'
    )
    transport__task_maximum_attempts: int = Field(
        5, description='Maximum number of transport task attempts before a Process is Paused.'
    )
    rmq__task_timeout: int = Field(10, description='Timeout in seconds for communications with RabbitMQ.')
    storage__sandbox: Optional[str] = Field(
        None, description='Absolute path to the directory to store sandbox folders.'
    )
    caching__default_enabled: bool = Field(False, description='Enable calculation caching by default.')
    caching__enabled_for: list[str] = Field([], description='Calculation entry points to enable caching on.')
    caching__disabled_for: list[str] = Field([], description='Calculation entry points to disable caching on.')

    @field_validator('caching__enabled_for', 'caching__disabled_for')
    @classmethod
    def validate_caching_identifier_pattern(cls, value: list[str]) -> list[str]:
        """Validate the caching identifier patterns."""
        from aiida.manage.caching import _validate_identifier_pattern

        for identifier in value:
            _validate_identifier_pattern(identifier=identifier, strict=True)
        return value


class GlobalOptionsSchema(ProfileOptionsSchema, defer_build=True):
    """Schema for the global options of an AiiDA instance."""

    autofill__user__email: Optional[str] = Field(
        None, description='Default user email to use when creating new profiles.'
    )
    autofill__user__first_name: Optional[str] = Field(
        None, description='Default user first name to use when creating new profiles.'
    )
    autofill__user__last_name: Optional[str] = Field(
        None, description='Default user last name to use when creating new profiles.'
    )
    autofill__user__institution: Optional[str] = Field(
        None, description='Default user institution to use when creating new profiles.'
    )
    rest_api__profile_switching: bool = Field(
        False, description='Toggle whether the profile can be specified in requests submitted to the REST API.'
    )
    warnings__development_version: bool = Field(
        True,
        description='Whether to print a warning when a profile is loaded while a development version is installed.',
    )


class ProfileStorageConfig(BaseModel, defer_build=True):
    """Schema for the storage backend configuration of an AiiDA profile."""

    backend: str
    config: dict[str, Any]


class ProcessControlConfig(BaseModel, defer_build=True):
    """Schema for the process control configuration of an AiiDA profile."""

    broker_protocol: str = Field('amqp', description='Protocol for connecting to the message broker.')
    broker_username: str = Field('guest', description='Username for message broker authentication.')
    broker_password: str = Field('guest', description='Password for message broker.')
    broker_host: str = Field('127.0.0.1', description='Hostname of the message broker.')
    broker_port: int = Field(5432, description='Port of the message broker.')
    broker_virtual_host: str = Field('', description='Virtual host to use for the message broker.')
    broker_parameters: dict[str, Any] = Field(
        default_factory=dict, description='Arguments to be encoded as query parameters.'
    )


class ProfileSchema(BaseModel, defer_build=True):
    """Schema for the configuration of an AiiDA profile."""

    uuid: str = Field(description='A UUID that uniquely identifies the profile.', default_factory=uuid4)
    storage: ProfileStorageConfig
    process_control: ProcessControlConfig
    default_user_email: Optional[str] = None
    test_profile: bool = False
    options: Optional[ProfileOptionsSchema] = None

    @field_serializer('uuid')
    def serialize_dt(self, value: UUID, _info):
        return str(value)


class ConfigSchema(BaseModel, defer_build=True):
    """Schema for the configuration of an AiiDA instance."""

    CONFIG_VERSION: Optional[ConfigVersionSchema] = None
    profiles: Optional[dict[str, ProfileSchema]] = None
    options: Optional[GlobalOptionsSchema] = None
    default_profile: Optional[str] = None
