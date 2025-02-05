"""Interface for a message broker that facilitates communication with and between process runners."""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from plumpy.controller import ProcessController

if TYPE_CHECKING:
    from plumpy.coordinator import Coordinator


__all__ = ('Broker',)


@runtime_checkable
class Broker(Protocol):
    """Interface for a message broker that facilitates communication with and between process runners."""

    @property
    def coordinator(self) -> 'Coordinator':
        """Return an instance of coordinator."""
        ...

    @property
    def controller(self) -> ProcessController:
        """Return the process controller"""
        ...

    def iterate_tasks(self):
        """Return an iterator over the tasks in the launch queue."""

    def close(self):
        """Close the broker."""
