###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Protocol as `Scheduler` contract."""

import typing as t

from aiida.common.lang import classproperty

if t.TYPE_CHECKING:
    from aiida.engine.processes.exit_code import ExitCode
    from aiida.schedulers.datastructures import JobInfo, JobResource, JobTemplate
    from aiida.transports import Transport

__all__ = ('Scheduler',)

class Scheduler(t.Protocol):
    """Protocol for a job scheduler."""

    @classmethod
    def preprocess_resources(cls, resources: dict[str, t.Any], default_mpiprocs_per_machine: int | None = None):
        """Pre process the resources.

        Add the `num_mpiprocs_per_machine` key to the `resources` if it is not already defined and it cannot be deduced
        from the `num_machines` and `tot_num_mpiprocs` being defined. The value is also not added if the job resource
        class of this scheduler does not accept the `num_mpiprocs_per_machine` keyword. Note that the changes are made
        in place to the `resources` argument passed.
        """
        ...

    @classmethod
    def validate_resources(cls, **resources: t.Any | None):
        """Validate the resources against the job resource class of this scheduler.

        :param resources: keyword arguments to define the job resources
        :raises ValueError: if the resources are invalid or incomplete
        """
        ...

    def get_feature(self, feature_name: str) -> bool: ...

    def get_submit_script(self, job_tmpl: JobTemplate) -> str:
        """Return the submit script as a string.

        :parameter job_tmpl: a `aiida.schedulers.datastrutures.JobTemplate` instance.

        The plugin returns something like

        #!/bin/bash <- this shebang line is configurable to some extent
        scheduler_dependent stuff to choose numnodes, numcores, walltime, ...
        prepend_computer [also from calcinfo, joined with the following?]
        prepend_code [from calcinfo]
        output of _get_script_main_content
        postpend_code
        postpend_computer
        """
        ...

    def submit_job(self, working_directory: str, filename: str) -> str | ExitCode:
        """Submit a job.

        :param working_directory: The absolute filepath to the working directory where the job is to be exectued.
        :param filename: The filename of the submission script relative to the working directory.
        :returns:
        """
        ...

    def get_jobs(
        self,
        jobs: list[str] | None = None,
        user: str | None = None,
        as_dict: bool = False,
    ) -> list[JobInfo] | dict[str, JobInfo]:
        """Return the list of currently active jobs.

        :param jobs: A list of jobs to check; only these are checked.
        :param user: A string with a user: only jobs of this user are checked.
        :param as_dict: If ``False`` (default), a list of ``JobInfo`` objects is returned. If ``True``, a dictionary is
            returned, where the ``job_id`` is the key and the values are the ``JobInfo`` objects.
        :returns: List of active jobs.
        """
        ...

    def kill_job(self, jobid: str) -> bool:
        """Kill a remote job and parse the return value of the scheduler to check if the command succeeded.

        ..note::

            On some schedulers, even if the command is accepted, it may take some seconds for the job to actually
            disappear from the queue.

        :param jobid: the job ID to be killed
        :returns: True if everything seems ok, False otherwise.
        """
        ...

    @property
    def transport(self) -> Transport:
        """Return the transport set for this scheduler."""
        ...

    def set_transport(self, transport: Transport):
        """Set the transport to be used to query the machine or to submit scripts.

        This class assumes that the transport is open and active.
        """
        ...

    @classproperty
    @classmethod
    def job_resource_class(cls) -> type[JobResource]:
        ...

    @classmethod
    def create_job_resource(cls, **kwargs: None | t.Any):
        """Create a suitable job resource from the kwargs specified."""
        ...

    def parse_output(
        self,
        detailed_job_info: dict[str, str | int] | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> ExitCode | None: ...

    def get_detailed_job_info(self, job_id: str) -> dict[str, str | int]:
        """Return the detailed job info.

        This will be a dictionary with the return value, stderr and stdout content returned by calling the command that
        is returned by `_get_detailed_job_info_command`.

        :param job_id: the job identifier
        :return: dictionary with `retval`, `stdout` and `stderr`.
        """
        ...

