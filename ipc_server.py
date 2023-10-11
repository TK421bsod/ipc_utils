import errno
import os
import time
from json import loads as json_serialize
from json import JSONDecodeError
import logging
import threading 

class IPCServer:

    __slots__ = ("_BUFFER_SIZE", "_NAME", "_logger", "_send", "_receive", "_global_lock", "_stop_event", "_ipc_thread", "_remote_shutdown")

    def __init__(self):
        #Don't allow writes or reads until we have everything set up.
        self._global_lock = threading.Lock()
        self._global_lock.acquire()
        self._logger = logging.getLogger("IPCServer")

    def initialize(self, name):
        self._logger.debug("Creating pipe.")
        self._remote_shutdown = False
        try:
            os.mkfifo(f"/tmp/{name}")
        except OSError:
            self._logger.error("Could not create pipe! Another IPCServer instance may not have shut down cleanly.")
            return
        self._logger.warn("Waiting for IPC client to initialize...")
        self._send = open(f"/tmp/{name}", "w")
        self._logger.warn("Connected to client. Opening client -> server channel...")
        self._receive = os.open(f"/tmp/{name}-reverse", os.O_RDONLY | os.O_NONBLOCK)
        self._NAME = name
        self._ipc_thread = threading.Thread(target=self.main_loop)
        self._stop_event = threading.Event()
        #Maximum bytes to read in a single os.read() call.
        self._BUFFER_SIZE = 1024
        self._global_lock.release()
        self._ipc_thread.start()
        self._logger.warn("IPC server initialized.")

    def shutdown_ipc(self):
        """Shut down the IPC thread. This must be called before the host application exits. Blocks until the IPC thread finishes."""
        self._stop_event.set()
        self._ipc_thread.join()

    def pre_shutdown(self):
        self._logger.warn("Shutting down.")
        self._global_lock.acquire()
        self._logger.debug("Stopping main loop.")
        if not self._stop_event.is_set():
            self._stop_event.set()

    def shutdown(self):
        self.pre_shutdown()
        self._logger.debug("Notifying the connected IPCClient.")
        self._send.write("{\"message\":\"remote_shutdown\"}")
        self._send.flush()
        time.sleep(0.1)
        #Close our write-only pipe.
        self._send.close()
        #Wait for client to respond with {"data":"finish_shutdown"}.
        self._logger.debug("Waiting for a response from the client...")
        ret = self.blocking_read()
        #Immediately after writing, the client should have closed its write-only pipe.
        #Now that we have shutdown confirmation, finish the shutdown.
        if ret['data'] == "finish_shutdown":
            self.do_shutdown()

    def remote_shutdown(self):
        self._logger.warn("Client is shutting down, bringing down serer")
        #Don't let the main loop run our normal shutdown method.
        self._remote_shutdown = True
        self.pre_shutdown()
        self._send.close()
        self.do_shutdown()

    def do_shutdown(self):
        self._logger.debug("Closing client -> server channel.")
        os.close(self._receive)
        time.sleep(0.1)
        self._logger.debug("Removing pipes.")
        os.remove(f"/tmp/{self._NAME}")
        os.remove(f"/tmp/{self._NAME}-reverse")
        self._logger.warn("Shutdown finished.")

    def blocking_read(self):
        while True:
            ret = self.read()
            if not ret:
                continue
            return ret

    def main_loop(self):
        self._logger.debug("Starting main loop.")
        while not self._stop_event.is_set():
            try:
                ret = self.read()
            except json.JSONDecodeError:
                print("Invalid data received.")
                continue
            if not ret:
                continue
            if ret.get('message'):
                getattr(self, ret.get('message'))()
            time.sleep(0.1)
        if not self._remote_shutdown:
            self.shutdown()

    def write(self, data):
        with self._global_lock:
            self._send.write(data)
            #Flush the write buffer to ensure data is written immediately.
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
