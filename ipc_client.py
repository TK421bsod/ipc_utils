import errno
import os
import time
from json import loads as json_serialize
from json import JSONDecodeError
import logging
import threading

class IPCClient:

    __slots__ = ("_BUFFER_SIZE", "_NAME", "_logger", "_stop_event", "_remote_shutdown", "_send", "_receive", "_callback", "_global_lock", "_ipc_thread")

    def __init__(self):
        #Don't allow writes or reads until we have everything set up.
        self._global_lock = threading.Lock()
        self._global_lock.acquire()
        self._logger = logging.getLogger("IPCClient")

    def try_open(self):
        try:
            #Open in non-blocking read-only mode.
            self._receive = os.open(f"/tmp/{self._NAME}", os.O_RDONLY | os.O_NONBLOCK)
            return True
        except FileNotFoundError:
            return False
        return False

    def shutdown_ipc(self):
        """Shut down the IPC thread. This must be called before the host application exits. Blocks until the IPC thread finishes."""
        self._stop_event.set()
        self._ipc_thread.join()

    def initialize(self, name, callback=None):
        self._logger.warn("IPC client initializing...")
        os.mkfifo(f"/tmp/{name}-reverse")
        self._logger.info("Connecting to server...")
        self._NAME = name
        self._remote_shutdown = False
        ret = None
        try:
            while not ret:
                time.sleep(0.01)
                ret = self.try_open()
        except KeyboardInterrupt:
            self._logger.error("Connection interrupted! Cleaning up.")
            os.remove(f"/tmp/{name}-reverse")
            quit()
        self._logger.info("Connected to server.")
        self._send = open(f"/tmp/{name}-reverse", "w")
        self._callback = callback
        if not callback:
            self._logger.warn("No callback passed to IPCClient.initialize!")
            self._logger.warn("Use IPCClient.register_callback to register one.")
        self._stop_event = threading.Event()
        self._ipc_thread = threading.Thread(target=self.main_loop)
        #Maximum bytes to read in a single os.read() call.
        self._BUFFER_SIZE = 1024
        self._global_lock.release()
        self._ipc_thread.start()
        print("IPC client initialized.")

    def register_callback(self, callback, overwrite=False):
        if self._callback and not overwrite:
            self._logger.warn("A callback is already registered. Pass overwrite=True to overwrite the existing callback.")
        self._callback = callback

    def pre_shutdown(self):
        self._logger.warn("Shutting down.")
        self._global_lock.acquire()
        self._logger.debug("Stopping main loop.")
        if not self._stop_event.is_set():
            self._stop_event.set()

    def remote_shutdown(self):
        self._logger.warn("Received shutdown request from the connected IPCServer.")
        self.pre_shutdown()
        self._remote_shutdown = True
        os.close(self._receive)
        #Tell the server we received the request and are ready to finish shutting down.
        self._send.write("{\"data\":\"finish_shutdown\"}")
        self._send.flush()
        #Then close the pipe. The server will take care of cleanup.
        self._send.close()
        self._logger.warn("Shutdown finished, stopping IPC thread")

    def shutdown(self):
        self.pre_shutdown()
        self._logger.debug("Notifying the connected IPCServer.")
        self._send.write("{\"message\":\"remote_shutdown\"}")
        self._send.flush()
        self._send.close()
        os.close(self._receive)
        self._logger.warn("Shutdown finished, stopping IPC thread")

    def main_loop(self):
        print("Starting main loop.")
        while not self._stop_event.is_set():
            try:
                ret = self.read()
            except JSONDecodeError:
                print("Invalid data received.")
                continue
            if not ret:
                pass
            elif ret.get('message'):
                getattr(self, ret.get('message'))()
            elif ret and self._callback:
                self._callback(ret)
            time.sleep(0.1)
        if not self._remote_shutdown:
            self.shutdown()

    def write(self, data):
        with self._global_lock:
            self._send.write(data)
            self._send.flush()

    def read(self):
        ret = None
        try:
            ret = os.read(self._receive, self._BUFFER_SIZE)
        except OSError as err:
            #"Try again" / "Operation would block"
            if err.errno == errno.EAGAIN or err.errno == errno.EWOULDBLOCK:
                pass
            else:
                raise
        if not ret:
            return ret
        self._logger.debug(f"Received data: {ret}")
        return json_serialize(ret.decode())
