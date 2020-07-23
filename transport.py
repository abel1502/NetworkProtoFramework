import logging
from typing import *
import abc
import socket
import selectors
import time


class NetworkError(Exception):
    pass


class Timeout(NetworkError):
    pass


class Transport(object):
    """
    A higher-level interface to a socket.

    This implements strict ways to read and write - that either do exactly what they're supposed to or throw an error
    """

    def __init__(self, sock, defaultTimeout=5.0):
        """
        :type sock: socket.socket
        :type defaultTimeout: float
        """
        self.socket = sock
        self.defaultTimeout = defaultTimeout
        self.socket.settimeout(self.defaultTimeout)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.socket, selectors.EVENT_READ | selectors.EVENT_WRITE)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def setTimeout(self, timeout):
        self.socket.settimeout(timeout)

    def resetTimeout(self):
        self.socket.settimeout(self.defaultTimeout)

    def write(self, data):
        """
        :type data: bytes
        """
        try:
            self.socket.sendall(data)
        except socket.timeout:
            raise Timeout("Transport.write")
        except socket.error as e:
            logging.debug("[ERROR] Transport.write {}", e)
            raise NetworkError("Transport.write", e)

    def read(self, amount):
        """
        :type amount: int
        :rtype: bytes
        """
        try:
            # MSG_WAITALL doesn't work on Windows, so now I have to do horrible things like this
            data = bytearray()
            oldTimeout = self.socket.gettimeout()
            deadline = time.monotonic() + oldTimeout
            while len(data) < amount:
                try:
                    data += self.socket.recv(amount)
                except socket.timeout:
                    pass
                interval = deadline - time.monotonic()
                self.socket.settimeout(interval)
                if interval <= 0:
                    self.socket.settimeout(oldTimeout)
                    raise Timeout("Transport.read")
            self.socket.settimeout(oldTimeout)
            return bytes(data)
        except socket.error as e:
            logging.debug("[ERROR] Transport.read {}", e)
            raise NetworkError("Transport.read", e)

    def close(self):
        self.socket.close()
        self.selector.close()

    def _isReady(self):
        _, events = self.selector.select(timeout=self.socket.gettimeout())[0]
        return events & selectors.EVENT_READ, events & selectors.EVENT_WRITE

    def hasData(self):
        return self._isReady()[0]

