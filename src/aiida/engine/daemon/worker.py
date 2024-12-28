###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Function that starts a daemon worker."""

import asyncio
import logging
import signal
import sys

from aiida.common.log import configure_logging
from aiida.engine.daemon.client import get_daemon_client
from aiida.engine.runners import Runner
from aiida.manage import get_config_option, get_manager
from aiida.manage.manager import Manager

LOGGER = logging.getLogger(__name__)


async def shutdown_worker(runner: Runner) -> None:
    """Cleanup tasks tied to the service's shutdown."""
    from asyncio import all_tasks, current_task

    LOGGER.info('Received signal to shut down the daemon worker')
    tasks = [task for task in all_tasks() if task is not current_task()]

    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    runner.close()

    LOGGER.info('Daemon worker stopped')

def create_daemon_runner(manager: Manager) -> 'Runner':
    """Create and return a new daemon runner.

    This is used by workers when the daemon is running and in testing.

    :param loop: the (optional) asyncio event loop to use

    :return: a runner configured to work in the daemon configuration

    """
    from plumpy.persistence import LoadSaveContext

    from aiida.engine import persistence
    from aiida.engine.processes.launcher import ProcessLauncher

    runner = manager.create_runner(broker_submit=True, loop=None)
    runner_loop = runner.loop

    # Listen for incoming launch requests
    task_receiver = ProcessLauncher(
        loop=runner_loop,
        persister=manager.get_persister(),
        load_context=LoadSaveContext(runner=runner),
        loader=persistence.get_object_loader(),
    )

    assert runner.coordinator is not None, 'coordinator not set for runner'
    runner.coordinator.add_task_subscriber(task_receiver)

    return runner

def start_daemon_worker(foreground: bool = False) -> None:
    """Start a daemon worker for the currently configured profile.

    :param foreground: If true, the logging will be configured to write to stdout, otherwise it will be configured to
        write to the daemon log file.
    """
    daemon_client = get_daemon_client()
    configure_logging(with_orm=True, daemon=not foreground, daemon_log_file=daemon_client.daemon_log_file)

    LOGGER.debug(f'sys.executable: {sys.executable}')
    LOGGER.debug(f'sys.path: {sys.path}')

    try:
        manager = get_manager()
        runner = create_daemon_runner(manager)
        manager.set_runner(runner)
    except Exception:
        LOGGER.exception('daemon worker failed to start')
        raise

    if isinstance(rlimit := get_config_option('daemon.recursion_limit'), int):
        LOGGER.info('Setting maximum recursion limit of daemon worker to %s', rlimit)
        sys.setrecursionlimit(rlimit)

    signals = (signal.SIGTERM, signal.SIGINT)
    for s in signals:
        # https://github.com/python/mypy/issues/12557
        runner.loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown_worker(runner)))  # type: ignore[misc]

    try:
        LOGGER.info('Starting a daemon worker')
        runner.start()
    except SystemError as exception:
        LOGGER.info('Received a SystemError: %s', exception)
        runner.close()

    LOGGER.info('Daemon worker started')
