###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Plugin for PBSPro.
This has been tested on PBSPro v. 12.
"""

import logging

from .pbsbaseclasses import PbsBaseClass
from aiida.engine.processes.exit_code import ExitCode

from aiida.common.escaping import escape_for_bash
from aiida.engine.processes.exit_code import ExitCode
from aiida.schedulers import SchedulerError
from aiida.schedulers.datastructures import JobInfo

_LOGGER = logging.getLogger(__name__)

# This maps PbsPro status letters to our own status list

## List of states from the man page of qstat
# B  Array job has at least one subjob running.
# E  Job is exiting after having run.
# F  Job is finished.
# H  Job is held.
# M  Job was moved to another server.
# Q  Job is queued.
# R  Job is running.
# S  Job is suspended.
# T  Job is being moved to new location.
# U  Cycle-harvesting job is suspended due to  keyboard  activity.
# W  Job is waiting for its submitter-assigned start time to be reached.
# X  Subjob has completed execution or has been deleted.


class PbsproScheduler(PbsBaseClass):
    """Subclass to support the PBSPro scheduler
    (http://www.pbsworks.com/).

    I redefine only what needs to change from the base class
    """

    ## I don't need to change this from the base class
    # _job_resource_class = PbsJobResource

    ## For the time being I use a common dictionary, should be sufficient
    ## for the time being, but I can redefine it if needed.
    # _map_status = _map_status_pbs_common

    def submit_job(self, working_directory: str, filename: str) -> str | ExitCode:
        """Submit a job.

        :param working_directory: The absolute filepath to the working directory where the job is to be executed.
        :param filename: The filename of the submission script relative to the working directory.
        """
        result = self.transport.exec_command_wait(
            self._get_submit_command(escape_for_bash(filename)), workdir=working_directory
        )
        return self._parse_submit_output(*result)

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
        with self.transport:
            retval, stdout, stderr = self.transport.exec_command_wait(self._get_joblist_command(jobs=jobs, user=user))

        joblist = self._parse_joblist_output(retval, stdout, stderr)
        if as_dict:
            jobdict = {job.job_id: job for job in joblist}
            if None in jobdict:
                raise SchedulerError('Found at least one job without jobid')
            return jobdict

        return joblist

    def kill_job(self, jobid: str) -> bool:
        """Kill a remote job and parse the return value of the scheduler to check if the command succeeded.

        ..note::

            On some schedulers, even if the command is accepted, it may take some seconds for the job to actually
            disappear from the queue.

        :param jobid: the job ID to be killed
        :returns: True if everything seems ok, False otherwise.
        """
        retval, stdout, stderr = self.transport.exec_command_wait(self._get_kill_command(jobid))
        return self._parse_kill_output(retval, stdout, stderr)

    def _get_resource_lines(
        self, num_machines, num_mpiprocs_per_machine, num_cores_per_machine, max_memory_kb, max_wallclock_seconds
    ):
        """Return the lines for machines, memory and wallclock relative
        to pbspro.
        """
        # Note: num_cores_per_machine is not used here but is provided by
        #       the parent class ('_get_submit_script_header') method

        return_lines = []

        select_string = f'select={num_machines}'
        if num_mpiprocs_per_machine:
            select_string += f':mpiprocs={num_mpiprocs_per_machine}'
        if num_cores_per_machine:
            select_string += f':ncpus={num_cores_per_machine}'

        if max_wallclock_seconds is not None:
            try:
                tot_secs = int(max_wallclock_seconds)
                if tot_secs <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    'max_wallclock_seconds must be ' "a positive integer (in seconds)! It is instead '{}'" ''.format(
                        max_wallclock_seconds
                    )
                )
            hours = tot_secs // 3600
            tot_minutes = tot_secs % 3600
            minutes = tot_minutes // 60
            seconds = tot_minutes % 60
            return_lines.append(f'#PBS -l walltime={hours:02d}:{minutes:02d}:{seconds:02d}')

        if max_memory_kb:
            try:
                physical_memory_kb = int(max_memory_kb)
                if physical_memory_kb <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f'max_memory_kb must be a positive integer (in kB)! It is instead `{max_memory_kb}`')
            select_string += f':mem={physical_memory_kb}kb'

        return_lines.append(f'#PBS -l {select_string}')
        return return_lines
