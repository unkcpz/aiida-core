###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Plugin for direct execution."""

from __future__ import annotations

from typing import Union

import aiida.schedulers
from aiida.common.escaping import escape_for_bash
from aiida.schedulers import SchedulerError
from aiida.schedulers.datastructures import JobInfo, JobState, NodeNumberJobResource
from aiida.schedulers.scheduler import Scheduler

from aiida.engine.processes.exit_code import ExitCode


## From the ps man page on Mac OS X 10.12
#     state     The state is given by a sequence of characters, for example,
#               ``RWNA''.  The first character indicates the run state of the
#               process:
#
#               I       Marks a process that is idle (sleeping for longer than
#                       about 20 seconds).
#               R       Marks a runnable process.
#               S       Marks a process that is sleeping for less than about 20
#                       seconds.
#               T       Marks a stopped process.
#               U       Marks a process in uninterruptible wait.
#               Z       Marks a dead process (a ``zombie'').

# From the man page of ps on Ubuntu 14.04:
#       Here are the different values that the s, stat and state output
#       specifiers (header "STAT" or "S") will display to describe the state of
#       a process:
#
#               D    uninterruptible sleep (usually IO)
#               R    running or runnable (on run queue)
#               S    interruptible sleep (waiting for an event to complete)
#               T    stopped, either by a job control signal or because it is
#                    being traced
#               W    paging (not valid since the 2.6.xx kernel)
#               X    dead (should never be seen)
#               Z    defunct ("zombie") process, terminated but not reaped by
#                    its parent

_MAP_STATUS_PS = {
    'D': JobState.RUNNING,
    'I': JobState.RUNNING,
    'R': JobState.RUNNING,
    'S': JobState.RUNNING,
    'T': JobState.SUSPENDED,
    'U': JobState.RUNNING,
    'W': JobState.RUNNING,
    'X': JobState.DONE,
    'Z': JobState.DONE,
    '?': JobState.UNDETERMINED,
    # `ps` can sometimes return `?` for the state of a process on macOS. This corresponds to an "unknown" state, see:
    #
    # https://apple.stackexchange.com/q/460394/497071
    #
    # Not sure about these three, I comment them out (they used to be in
    # here, but they don't appear neither on ubuntu nor on Mac)
    #    'F': JobState.DONE,
    #    'H': JobState.QUEUED_HELD,
    #    'Q': JobState.QUEUED,
}


class DirectJobResource(NodeNumberJobResource):
    """An implementation of JobResource for the direct excution bypassing schedulers."""

    @classmethod
    def accepts_default_memory_per_machine(cls):
        """Return True if this subclass accepts a `default_memory_per_machine` key, False otherwise."""
        return False


class DirectScheduler(Scheduler):
    """Support for the direct execution bypassing schedulers."""

    _logger = aiida.schedulers.Scheduler._logger.getChild('direct')

    # Query only by list of jobs and not by user
    _features = {
        'can_query_by_user': True,
    }

    # The class to be used for the job resource.
    _job_resource_class = DirectJobResource

    def submit_job(self, working_directory: str, filename: str) -> str | ExitCode:
        """Submit a job.

        :param working_directory: The absolute filepath to the working directory where the job is to be executed.
        :param filename: The filename of the submission script relative to the working directory.
        """
        submit_script = escape_for_bash(filename)
        submit_command = f'bash {submit_script} > /dev/null 2>&1 & echo $!'

        self.logger.info(f'submitting with: {submit_command}')

        retval, stdout, stderr = self.transport.exec_command_wait(submit_command, workdir=working_directory)

        if retval != 0:
            self.logger.error(f'Error in _parse_submit_output: retval={retval}; stdout={stdout}; stderr={stderr}')
            raise SchedulerError(f'Error during submission, retval={retval}\nstdout={stdout}\nstderr={stderr}')

        if stderr.strip():
            self.logger.warning(
                f'in _parse_submit_output for {self.transport!s}: there was some text in stderr: {stderr}'
            )

        if not stdout.strip():
            self.logger.debug(f'Unable to get the PID: retval={retval}; stdout={stdout}; stderr={stderr}')
            raise SchedulerError(f'Unable to get the PID: retval={retval}; stdout={stdout}; stderr={stderr}')

        return stdout.strip()

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
        import re

        # TODO: in the case of job arrays, decide what to do (i.e., if we want to pass the -t options to list each subjob).

        # Using subprocess.Popen with `start_new_session=True` (as done in both local and ssh transport) results in
        # processes without a controlling terminal.
        # The -x option tells ps to include processes which do not have a controlling terminal, which would not be
        # listed otherwise (leading the direct scheduler to conclude that the process already completed).
        command = 'ps -xo pid,stat,user,time'

        if jobs:
            if isinstance(jobs, str):
                command += f' {escape_for_bash(jobs)}'
            else:
                try:
                    command += f" {' '.join(escape_for_bash(job) for job in jobs if job)}"
                except TypeError:
                    raise TypeError("If provided, the 'jobs' variable must be a string or a list of strings")

        command += '| tail -n +2'  # -header, do not use 'h'

        with self.transport:
            retval, stdout, stderr = self.transport.exec_command_wait(command)

        # FIXME: I am very lenghty, move me into the scheduler parser component
        # Parsing the output of get job command
        filtered_stderr = '\n'.join(line for line in stderr.split('\n'))
        if filtered_stderr.strip():
            self.logger.warning(f"Warning in _parse_joblist_output, non-empty (filtered) stderr='{filtered_stderr}'")
            if retval != 0:
                raise SchedulerError('Error during direct execution parsing (_parse_joblist_output function)')

        # Create dictionary and parse specific fields
        job_list = []
        for line in stdout.split('\n'):
            if re.search(r'^\s*PID', line) or line == '':
                # Skip the header if present
                continue
            line = re.sub(r'^\s+', '', line)  # noqa: PLW2901
            job = re.split(r'\s+', line)
            this_job = JobInfo()
            this_job.job_id = job[0]

            if len(job) < 3:
                raise SchedulerError(f"Unexpected output from the scheduler, not enough fields in line '{line}'")

            try:
                job_state_string = job[1][0]  # I just check the first character
            except IndexError:
                self.logger.debug(f"No 'job_state' field for job id {this_job.job_id}")
                this_job.job_state = JobState.UNDETERMINED
            else:
                try:
                    this_job.job_state = _MAP_STATUS_PS[job_state_string]
                except KeyError:
                    self.logger.warning(f"Unrecognized job_state '{job_state_string}' for job id {this_job.job_id}")
                    this_job.job_state = JobState.UNDETERMINED

            try:
                # I strip the part after the @: is this always ok?
                this_job.job_owner = job[2]
            except KeyError:
                self.logger.debug(f"No 'job_owner' field for job id {this_job.job_id}")

            try:
                string = job[3]
                pieces = re.split('[:.]', string)
                if len(pieces) != 3:
                    self.logger.warning(f'Wrong number of pieces (expected 3) for time string {string}')
                    raise ValueError('Wrong number of pieces for time string.')

                days = 0
                pieces_first = pieces[0].split('-')

                if len(pieces_first) == 2:
                    days, pieces[0] = pieces_first
                    days = int(days)

                try:
                    hours = int(pieces[0])
                    if hours < 0:
                        raise ValueError
                except ValueError:
                    self.logger.warning(f'Not a valid number of hours: {pieces[0]}')
                    raise ValueError('Not a valid number of hours.')

                try:
                    mins = int(pieces[1])
                    if mins < 0:
                        raise ValueError
                except ValueError:
                    self.logger.warning(f'Not a valid number of minutes: {pieces[1]}')
                    raise ValueError('Not a valid number of minutes.')

                try:
                    secs = int(pieces[2])
                    if secs < 0:
                        raise ValueError
                except ValueError:
                    self.logger.warning(f'Not a valid number of seconds: {pieces[2]}')
                    raise ValueError('Not a valid number of seconds.')

                this_job.wallclock_time_seconds = days * 86400 + hours * 3600 + mins * 60 + secs
            except KeyError:
                # May not have started yet
                pass
            except ValueError:
                self.logger.warning(f"Error parsing 'resources_used.walltime' for job id {this_job.job_id}")

            # I append to the list of jobs to return
            job_list.append(this_job)

        found_jobs = []
        found_jobs = [j.job_id for j in job_list]

        # Now check if there are any the user requested but were not found
        not_found_jobs = list(set(jobs) - set(found_jobs)) if jobs else []

        for job_id in not_found_jobs:
            job = JobInfo()
            job.job_id = job_id
            job.job_state = JobState.DONE
            # Owner and wallclock time is unknown
            job_list.append(job)

        return job_list

    def kill_job(self, jobid: str) -> bool:
        """Kill a remote job and parse the return value of the scheduler to check if the command succeeded.

        ..note::

            On some schedulers, even if the command is accepted, it may take some seconds for the job to actually
            disappear from the queue.

        :param jobid: the job ID to be killed
        :returns: True if everything seems ok, False otherwise.
        """
        from psutil import Process

        # get a list of the process id of all descendants
        process = Process(int(jobid))
        children = process.children(recursive=True)
        jobids = [str(jobid)]
        jobids.extend([str(child.pid) for child in children])
        jobids_str = ' '.join(jobids)

        kill_command = f'kill {jobids_str}'

        self.logger.info(f'killing job {jobid}')

        retval, stdout, stderr = self.transport.exec_command_wait(kill_command)

        # parsing the kill command output
        if retval != 0:
            self.logger.error(f'Error in _parse_kill_output: retval={retval}; stdout={stdout}; stderr={stderr}')
            return False

        if stderr.strip():
            self.logger.warning(
                f'in _parse_kill_output for {self.transport!s}: there was some text in stderr: {stderr}'
            )

        if stdout.strip():
            self.logger.warning(
                f'in _parse_kill_output for {self.transport!s}: there was some text in stdout: {stdout}'
            )

        return True

    def _get_submit_script_header(self, job_tmpl):
        """Return the submit script header, using the parameters from the
        job_tmpl.

        Args:
        -----
           job_tmpl: an JobTemplate instance with relevant parameters set.
        """
        lines = []
        empty_line = ''

        # Redirecting script output on the correct files
        # Should be one of the first commands
        if job_tmpl.sched_output_path:
            lines.append(f'exec > {job_tmpl.sched_output_path}')

        if job_tmpl.sched_join_files:
            # TODO: manual says:
            # By  default both standard output and standard error are directed
            # to a file of the name "slurm-%j.out", where the "%j" is replaced
            # with  the  job  allocation  number.
            # See that this automatic redirection works also if
            # I specify a different --output file
            if job_tmpl.sched_error_path:
                self.logger.info('sched_join_files is True, but sched_error_path is set; ignoring sched_error_path')
        elif job_tmpl.sched_error_path:
            lines.append(f'exec 2> {job_tmpl.sched_error_path}')
        else:
            # To avoid automatic join of files
            lines.append('exec 2>&1')

        if job_tmpl.max_memory_kb:
            self.logger.warning('Physical memory limiting is not supported by the direct scheduler.')

        if not job_tmpl.import_sys_environment:
            lines.append('env --ignore-environment \\')

        if job_tmpl.custom_scheduler_commands:
            lines.append(job_tmpl.custom_scheduler_commands)

        if job_tmpl.job_resource and job_tmpl.job_resource.num_cores_per_mpiproc:
            lines.append(f'export OMP_NUM_THREADS={job_tmpl.job_resource.num_cores_per_mpiproc}')

        if job_tmpl.rerunnable:
            self.logger.warning(
                "The 'rerunnable' option is set to 'True', but has no effect when using the direct scheduler."
            )

        lines.append(empty_line)

        ## The following code is not working as there's an empty line
        ## inserted between the header and the actual command.
        # if job_tmpl.max_wallclock_seconds is not None:
        #     try:
        #         tot_secs = int(job_tmpl.max_wallclock_seconds)
        #         if tot_secs <= 0:
        #             raise ValueError
        #     except ValueError:
        #         raise ValueError(
        #             "max_wallclock_seconds must be "
        #             "a positive integer (in seconds)! It is instead '{}'"
        #             "".format((job_tmpl.max_wallclock_seconds)))
        #     lines.append("timeout {} \\".format(tot_secs))

        return '\n'.join(lines)

