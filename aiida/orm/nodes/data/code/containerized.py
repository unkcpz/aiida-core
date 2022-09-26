# -*- coding: utf-8 -*-
###########################################################################
# Copyright (c), The AiiDA team. All rights reserved.                     #
# This file is part of the AiiDA code.                                    #
#                                                                         #
# The code is hosted on GitHub at https://github.com/aiidateam/aiida-core #
# For further information on the license, see the LICENSE.txt file        #
# For further information please visit http://www.aiida.net               #
###########################################################################
"""Data plugins representing an executable code to be run in a container.
These plugins are directly analogous to the ``InstalledCode`` and ``PortableCode`` plugins, except that the executable
is present inside of a container. For the ``InstalledContainerizedCode`` the executable is expected to already be
present inside a container that is available on the target computer. With the ``PortableContainerizedCode`` plugin, the
target executable will be stored in AiiDA's storage, just as with the ``PortableCode`` and when launched, the code will
be copied inside the container on the target computer and run inside the container.
	"""
import click

from aiida.common.lang import type_check

from .abstract import AbstractCode
from .installed import InstalledCode
from .portable import PortableCode

__all__ = (
    'InstalledContainerizedCode',
    'PortableContainerizedCode',
)


class Containerized(AbstractCode):
    """Containerized Mixin for code that can run on container"""
    _KEY_ATTRIBUTE_ENGINE_COMMAND: str = 'engine_command'
    _KEY_ATTRIBUTE_IMAGE: str = 'image'

    def __init__(self, engine_command: str, image: str, **kwargs):
        super().__init__(**kwargs)
        self.engine_command = engine_command
        self.image = image

    @property
    def engine_command(self) -> str:
        """Return the engine command with image as template field of the containerized code
        :return: The engine command of the containerized code
        """
        return self.base.attributes.get(self._KEY_ATTRIBUTE_ENGINE_COMMAND)

    @engine_command.setter
    def engine_command(self, value: str) -> None:
        """Set the engine command of the containerized code
        :param value: The engine command of the containerized code
        """
        type_check(value, str)

        if '{image}' not in value:
            raise ValueError("the '{image}' template field should be in engine command.")

        self.base.attributes.set(self._KEY_ATTRIBUTE_ENGINE_COMMAND, value)

    @property
    def image(self) -> str:
        """The image of container
        :return: The image of container.
        """
        return self.base.attributes.get(self._KEY_ATTRIBUTE_IMAGE)

    @image.setter
    def image(self, value: str) -> None:
        """Set the image name of container
        :param value: The image name of container.
        """
        type_check(value, str)

        self.base.attributes.set(self._KEY_ATTRIBUTE_IMAGE, value)

    def get_engine_command(self) -> str:
        """Return the engine command with image field set with image name.
        :return: The engine command in script job with image field set with the image name.
        """
        cmdline = self.engine_command.format(image=self.image)

        return cmdline.split()

    def get_mpirun_command(self) -> list:
        """Return the mpi_args in terms of code."""
        mpi_args = self.mpi_args

        return mpi_args.split()

    @classmethod
    def _get_cli_options(cls) -> dict:
        """Return the CLI options that would allow to create an instance of this class."""
        options = {
            'engine_command': {
                'required':
                True,
                'prompt':
                'Engine command',
                'help': (
                    'The command to run the container. It must contain the placeholder '
                    '{image} that will be replaced with the `image_name`.'
                ),
                'type':
                click.STRING,
            },
            'image': {
                'required': True,
                'type': click.STRING,
                'prompt': 'Image',
                'help': 'Name of the image container in which to the run the executable.',
            },
        }
        options.update(**super()._get_cli_options())

        return options


class InstalledContainerizedCode(Containerized, InstalledCode):
    """Data plugin representing an executable code in container on a remote computer."""


class PortableContainerizedCode(Containerized, PortableCode):
    """Data plugin representing an executable code stored in AiiDA's storage to be run in a container."""
