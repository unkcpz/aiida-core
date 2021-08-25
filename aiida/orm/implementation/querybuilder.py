# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Abstract `QueryBuilder` definition."""
import abc
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Union, TYPE_CHECKING

from aiida.common.lang import type_check
from aiida.common.log import AIIDA_LOGGER

try:
    from typing import Literal, TypedDict  # pylint: disable=ungrouped-imports
except ImportError:
    # Python <3.8 backport
    from typing_extensions import Literal, TypedDict  # type: ignore

if TYPE_CHECKING:
    from aiida.orm.implementation import Backend

__all__ = ('BackendQueryBuilder',)

QUERYBUILD_LOGGER = AIIDA_LOGGER.getChild('export')


class EntityTypes(Enum):
    """The entity types and their allowed relationships."""
    AUTHINFO = 'authinfo'
    COMMENT = 'comment'
    COMPUTER = 'computer'
    GROUP = 'group'
    LOG = 'log'
    NODE = 'node'
    USER = 'user'


EntityRelationships: Dict[str, Set[str]] = {
    'authinfo': set(),
    'comment': {'with_node', 'with_user'},
    'computer': {'with_node'},
    'group': {'with_node', 'with_user'},
    'log': {'with_node'},
    'node': {
        'with_comment', 'with_log', 'with_incoming', 'with_outgoing', 'with_descendants', 'with_ancestors',
        'with_computer', 'with_user', 'with_group'
    },
    'user': {'with_comment', 'with_group', 'with_node'}
}


class PathItemType(TypedDict):
    """An item on the query path"""

    entity_type: Union[str, List[str]]
    # this can be derived from the entity_type, but it is more efficient to store
    orm_base: Literal['node', 'group', 'authinfo', 'comment', 'computer', 'log', 'user']
    tag: str
    joining_keyword: str
    joining_value: str
    outerjoin: bool
    edge_tag: str


class QueryDictType(TypedDict):
    """A JSON serialisable representation of a ``QueryBuilder`` instance"""

    path: List[PathItemType]
    # mapping: tag -> 'and' | 'or' | '~or' | '~and' | '!and' | '!or' -> [] -> operator -> value
    #              -> operator -> value
    filters: Dict[str, Dict[str, Union[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]]]
    # mapping: tag -> [] -> field -> 'func' -> 'max' | 'min' | 'count'
    #                                'cast' -> 'b' | 'd' | 'f' | 'i' | 'j' | 't'
    project: Dict[str, List[Dict[str, Dict[str, Any]]]]
    # list of mappings: tag  -> [] -> field -> 'order' -> 'asc' | 'desc'
    #                                          'cast'  -> 'b' | 'd' | 'f' | 'i' | 'j' | 't'
    order_by: List[Dict[str, List[Dict[str, Dict[str, str]]]]]
    offset: Optional[int]
    limit: Optional[int]
    distinct: bool


# This global variable is necessary to enable the subclassing functionality for the `Group` entity. The current
# implementation of the `QueryBuilder` was written with the assumption that only `Node` was subclassable. Support for
# subclassing was added later for `Group` and is based on its `type_string`, but the current implementation does not
# allow to extend this support to the `QueryBuilder` in an elegant way. The prefix `group.` needs to be used in various
# places to make it work, but really the internals of the `QueryBuilder` should be rewritten to in principle support
# subclassing for any entity type. This workaround should then be able to be removed.
GROUP_ENTITY_TYPE_PREFIX = 'group.'


class BackendQueryBuilder:
    """Backend query builder interface"""

    def __init__(self, backend: 'Backend'):
        """
        :param backend: the backend
        """
        from . import backends
        type_check(backend, backends.Backend)
        self._backend = backend

    @abc.abstractmethod
    def yield_per(self, data: QueryDictType, batch_size: int):
        """
        :param int batch_size: Number of rows to yield per step

        Yields *count* rows at a time

        :returns: a generator
        """

    @abc.abstractmethod
    def count(self, data: QueryDictType) -> int:
        """Return the number of results of the query"""

    @abc.abstractmethod
    def first(self, data: QueryDictType) -> Optional[List[Any]]:
        """Executes query, asking for one instance.

        :returns: One row of aiida results
        """

    @abc.abstractmethod
    def iterall(self, data: QueryDictType, batch_size: Optional[int]) -> Iterable[List[Any]]:
        """Return an iterator over all the results of a list of lists."""

    @abc.abstractmethod
    def iterdict(self, data: QueryDictType, batch_size: Optional[int]) -> Iterable[Dict[str, Dict[str, Any]]]:
        """Return an iterator over all the results of a list of dictionaries."""

    def as_sql(self, data: QueryDictType, inline: bool = False) -> str:
        """Convert the query to an SQL string representation.

        .. warning::

            This method should be used for debugging purposes only,
            since normally sqlalchemy will handle this process internally.

        :params inline: Inline bound parameters (this is normally handled by the Python DBAPI).
        """
        raise NotImplementedError

    def analyze_query(self, data: QueryDictType, execute: bool = True, verbose: bool = False) -> str:
        """Return the query plan, i.e. a list of SQL statements that will be executed.

        See: https://www.postgresql.org/docs/11/sql-explain.html

        :params execute: Carry out the command and show actual run times and other statistics.
        :params verbose: Display additional information regarding the plan.
        """
        raise NotImplementedError
