"""Temporary Live control surface: subprocess/pipe test, never sends keys or MIDI."""

import importlib
import os
import sys
import time

from ableton.v2.base import task
from ableton.v2.control_surface import ControlSurface


SOURCE = '''ObjC.import("Foundation");
var input = $.NSFileHandle.fileHandleWithStandardInput;
var output = $.NSFileHandle.fileHandleWithStandardOutput;
while (true) {
    var data = input.availableData;
    if (Number(data.length) === 0) break;
    output.writeData(data);
}'''


def create_instance(c_instance):
    return RuntimeProbe(c_instance=c_instance)


class RuntimeProbe(ControlSurface):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._child = None
        self._done = False
        self._received = b""
        self._errors = b""
        self._sent = False
        self._eof_sent = False
        self._started = time.monotonic()
        try:
            self.log_message("LCXL3_JXA_PROBE python=" + sys.version.replace("\n", " "))
            for name in ("subprocess", "_posixsubprocess", "select", "fcntl", "threading"):
                importlib.import_module(name)
                self.log_message("LCXL3_JXA_PROBE import_ok=" + name)
            import subprocess
            self._child = subprocess.Popen(
                ["/usr/bin/osascript", "-l", "JavaScript", "-e", SOURCE],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0, close_fds=True,
            )
            for stream in (self._child.stdin, self._child.stdout, self._child.stderr):
                os.set_blocking(stream.fileno(), False)
            self.log_message("LCXL3_JXA_PROBE child_pid=" + str(self._child.pid))
            self._tasks.add(task.loop(task.sequence(task.run(self._tick), task.delay(0.1))))
        except Exception as error:
            self._finish("FAIL " + repr(error))

    def _tick(self):
        if self._done:
            return
        try:
            child = self._child
            if not self._sent:
                payload = b"LCXL3_JXA_PROBE_ECHO\n"
                try:
                    count = os.write(child.stdin.fileno(), payload)
                except BlockingIOError:
                    count = 0
                if count == len(payload):
                    self._sent = True
                elif count:
                    raise RuntimeError("partial probe write")
            for stream, attribute in ((child.stdout, "_received"), (child.stderr, "_errors")):
                try:
                    data = os.read(stream.fileno(), 4096)
                except BlockingIOError:
                    data = b""
                setattr(self, attribute, (getattr(self, attribute) + data)[-8192:])
            if self._received == b"LCXL3_JXA_PROBE_ECHO\n" and not self._eof_sent:
                child.stdin.close()
                self._eof_sent = True
                self.log_message("LCXL3_JXA_PROBE echo_ok; stdin closed")
            result = child.poll()
            if result is not None:
                if result == 0 and self._eof_sent:
                    self._finish("PASS subprocess + nonblocking pipes + echo + EOF exit")
                else:
                    self._finish("FAIL exit={} stderr={}".format(result, self._errors.decode("utf-8", "replace")))
            elif time.monotonic() - self._started > 5.0:
                self._finish("FAIL timeout")
        except Exception as error:
            self._finish("FAIL " + repr(error))

    def _finish(self, message):
        self._done = True
        self.log_message("LCXL3_JXA_PROBE " + message)
        self._cleanup()

    def _cleanup(self):
        child = self._child
        if child is None:
            return
        if child.poll() is None:
            child.kill()
            # Reap only this diagnostic child away from Live's callback thread.
            import threading
            threading.Thread(target=child.wait, daemon=True).start()
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()
        self._child = None

    def disconnect(self):
        self._done = True
        self._cleanup()
        super().disconnect()
