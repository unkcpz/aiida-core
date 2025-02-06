# -*- coding: utf-8 -*-
"""In memory coordinator"""
import sys
from typing import Any
import concurrent.futures

from plumpy.exceptions import CoordinatorConnectionError
from plumpy.rmq import TaskRejected
import shortuuid


class PhantomCoordinator:
    def __init__(self):
        self._task_subscribers = {}
        self._broadcast_subscribers = {}
        self._rpc_subscribers = {}
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True
        del self._task_subscribers
        del self._broadcast_subscribers
        del self._rpc_subscribers

    def add_rpc_subscriber(self, subscriber, identifier=None) -> Any:
        self._ensure_open()
        identifier = identifier or shortuuid.uuid()
        if identifier in self._rpc_subscribers:
            raise RuntimeError(f"Duplicate RPC subscriber with identifier '{identifier}'")
        self._rpc_subscribers[identifier] = subscriber
        return identifier

    def remove_rpc_subscriber(self, identifier):
        self._ensure_open()
        try:
            self._rpc_subscribers.pop(identifier)
        except KeyError as exc:
            raise ValueError(f"Unknown subscriber '{identifier}'") from exc

    def add_task_subscriber(self, subscriber, identifier=None):
        """
        Register a task subscriber

        :param subscriber: The task callback function
        :param identifier: the subscriber identifier
        """
        self._ensure_open()
        identifier = identifier or shortuuid.uuid()
        if identifier in self._rpc_subscribers:
            raise RuntimeError(f"Duplicate RPC subscriber with identifier '{identifier}'")
        self._task_subscribers[identifier] = subscriber
        return identifier

    def remove_task_subscriber(self, identifier):
        """
        Remove a task subscriber

        :param identifier: the subscriber to remove
        :raises: ValueError if identifier does not correspond to a known subscriber
        """
        self._ensure_open()
        try:
            self._task_subscribers.pop(identifier)
        except KeyError as exception:
            raise ValueError(f"Unknown subscriber: '{identifier}'") from exception

    def add_broadcast_subscriber(self, subscriber, subject_filters=None, sender_filters=None, identifier=None) -> Any:
        self._ensure_open()
        identifier = identifier or shortuuid.uuid()
        if identifier in self._broadcast_subscribers:
            raise RuntimeError(f"Duplicate RPC subscriber with identifier '{identifier}'")

        self._broadcast_subscribers[identifier] = subscriber
        return identifier

    def remove_broadcast_subscriber(self, identifier):
        self._ensure_open()
        try:
            del self._broadcast_subscribers[identifier]
        except KeyError as exception:
            raise ValueError(f"Broadcast subscriber '{identifier}' unknown") from exception

    def task_send(self, msg, no_reply=False):
        self._ensure_open()
        future = concurrent.futures.Future()

        for subscriber in self._task_subscribers.values():
            try:
                result = subscriber(self, msg)
                future.set_result(result)
                break
            except TaskRejected:
                pass
            except Exception:
                future.set_exception(RuntimeError(sys.exc_info()))
                break

        if no_reply:
            return None

        return future

    def rpc_send(self, recipient_id, msg):
        self._ensure_open()
        try:
            subscriber = self._rpc_subscribers[recipient_id]
        except KeyError as exception:
            raise RuntimeError(f"Unknown rpc recipient '{recipient_id}'") from exception
        else:
            future = concurrent.futures.Future()
            try:
                future.set_result(subscriber(self, msg))
            except Exception:
                future.set_exception(RuntimeError(sys.exc_info()))

            return future

    def broadcast_send(self, body, sender=None, subject=None, correlation_id=None):
        self._ensure_open()
        for subscriber in self._broadcast_subscribers.values():
            subscriber(self, body=body, sender=sender, subject=subject, correlation_id=correlation_id)
        return True

    def _ensure_open(self):
        if self.is_closed():
            raise CoordinatorConnectionError
