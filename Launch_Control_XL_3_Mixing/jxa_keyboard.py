"""Nonblocking transport to the macOS standard JXA keyboard worker.

No process is started while importing this module.  The surface calls start()
once and poll() from its normal update task; input callbacks never wait for an
acknowledgement or queue a second key press.
"""

import errno
import json
import logging
import math
import os
import sys
import time


logger = logging.getLogger(__name__)


class JxaKeyboardSender(object):
    START_TIMEOUT = 3.0
    ACK_TIMEOUT = 0.5
    STATUS_INTERVAL = 0.1
    STATE_MAX_AGE = 0.25
    PRESS_TTL = 0.05
    MAX_LINE_BYTES = 1024
    MAX_READS_PER_POLL = 4
    RESULT_STATUSES = frozenset((
        "posted", "diagnostic", "expired", "background",
        "permission_denied", "cancelled", "invalid", "error",
    ))

    def __init__(self, process_factory=None, clock=None, platform=None, pid=None,
                 worker_path=None, diagnostic=False, log=None):
        self._process_factory = process_factory
        self._clock = clock or time.monotonic
        self._platform = sys.platform if platform is None else platform
        self._pid = os.getpid() if pid is None else pid
        self._worker_path = worker_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "keyboard_worker.js")
        self._diagnostic = bool(diagnostic)
        self._logger = log or logger
        self._process = None
        self._reaper_event = None
        self._reaper_context = None
        self._reaper_started = False
        self._fds = {}
        self._started = False
        self._closed = False
        self._failed = False
        self._ready = False
        self._started_at = None
        self._last_state_at = None
        self._last_status_at = None
        self._status_pending_at = None
        self._frontmost = False
        self._allowed = False
        self._effective_frontmost = False
        self._worker_focus_epoch = None
        self._focus_epoch = 0
        self._generation = 0
        self._sequence = 0
        self._pending_press = None
        self._stdout_buffer = b""
        self._stderr_tail = b""
        self._permission_logged = False
        self._polling = False

    @property
    def focus_epoch(self):
        """Changes even when the worker observes an out-and-back focus change."""
        return self._focus_epoch

    def start(self):
        if self._started or self._closed:
            return self._process is not None and not self._failed
        self._started = True
        if self._platform != "darwin":
            self._fail("unsupported_platform: %s" % self._platform)
            return False
        child_fds = []
        try:
            # Import failures in Live's embedded Python disable only this feature.
            import subprocess
            import threading
            # Establish cleanup before creating the child. If Live cannot start
            # threads, initialization fails without leaving a process to reap.
            self._reaper_event = threading.Event()
            self._reaper_context = {"process": None, "fds": []}
            reaper = threading.Thread(
                target=self._await_cleanup,
                args=(self._reaper_event, self._reaper_context,
                      subprocess.TimeoutExpired),
                name="LCXL3-keyboard-reaper")
            reaper.daemon = True
            reaper.start()
            self._reaper_started = True
            factory = self._process_factory or subprocess.Popen
            input_read, input_write = self._make_pipe()
            self._fds["stdin"] = input_write
            child_fds.append(input_read)
            output_read, output_write = self._make_pipe()
            self._fds["stdout"] = output_read
            child_fds.append(output_write)
            error_read, error_write = self._make_pipe()
            self._fds["stderr"] = error_read
            child_fds.append(error_write)
            arguments = ["/usr/bin/osascript", "-l", "JavaScript",
                         self._worker_path, str(self._pid)]
            if self._diagnostic:
                arguments.append("--diagnostic")
            self._started_at = self._clock()
            self._process = factory(
                arguments, stdin=input_read, stdout=output_write,
                stderr=error_write, shell=False, close_fds=True, bufsize=0)
            self._reaper_context["process"] = self._process
            self._logger.info("LCXL3 keyboard navigation: worker_starting")
            return True
        except Exception as error:
            self._fail("initialization_failed: %s" % error)
            return False
        finally:
            for fd in child_fds:
                self._close_fd(fd)

    @staticmethod
    def _make_pipe():
        read_fd, write_fd = os.pipe()
        try:
            os.set_blocking(read_fd, False)
            os.set_blocking(write_fd, False)
        except Exception:
            os.close(read_fd)
            os.close(write_fd)
            raise
        return read_fd, write_fd

    def is_frontmost(self):
        self.poll()
        return self._effective_frontmost

    def press(self, direction, at=None):
        if at is None:
            at = self._clock()
        if type(direction) is not int or direction not in (-1, 1):
            return False
        if type(at) not in (int, float) or not math.isfinite(at):
            return False
        # Keep the timestamp captured at MIDI callback entry. Navigation's
        # focus checks may already have consumed most or all of its lifetime.
        if self._clock() - at >= self.PRESS_TTL:
            return False
        self.poll()
        if (not self._effective_frontmost or self._pending_press is not None
                or self._clock() - at >= self.PRESS_TTL):
            return False
        sequence = self._sequence + 1
        message = {"type": "press", "seq": sequence,
                   "generation": self._generation, "at": at,
                   "direction": direction,
                   "focus_epoch": self._worker_focus_epoch}
        if not self._write_message(message):
            return False
        self._sequence = sequence
        self._pending_press = (sequence, self._generation, at)
        return True

    def cancel(self):
        # No queued or in-flight input exists before startup or while idle.
        # A pending request already in an older generation is already cancelled.
        if (self._pending_press is None
                or self._pending_press[1] != self._generation):
            return
        self._generation += 1
        if self._process is not None and not self._failed and not self._closed:
            self._write_message({"type": "cancel", "generation": self._generation})

    def poll(self):
        if self._process is None or self._closed or self._failed or self._polling:
            return
        self._polling = True
        try:
            self._drain_stderr()
            self._drain_stdout()
            if self._failed:
                return
            if self._process.poll() is not None:
                self._fail("worker_exited")
                return
            now = self._clock()
            if not self._ready:
                if now - self._started_at >= self.START_TIMEOUT:
                    self._fail("startup_timeout")
                return
            if (self._pending_press is not None
                    and now - self._pending_press[2] >= self.ACK_TIMEOUT):
                self._fail("key_acknowledgement_timeout")
                return
            if (self._status_pending_at is not None
                    and now - self._status_pending_at >= self.ACK_TIMEOUT):
                self._fail("status_timeout")
                return
            self._update_effective_frontmost(now)
            if (self._status_pending_at is None
                    and (self._last_status_at is None
                         or now - self._last_status_at >= self.STATUS_INTERVAL)):
                if self._write_message({"type": "status"}):
                    self._status_pending_at = now
                    self._last_status_at = now
        except Exception as error:
            self._fail("transport_failed: %s" % error)
        finally:
            self._polling = False

    def _write_message(self, message):
        if self._process is None or self._closed or self._failed:
            return False
        try:
            data = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
            if len(data) > self.MAX_LINE_BYTES:
                raise ValueError("outgoing_message_too_large")
            # Small pipe writes are atomic; a partial write is treated as a fault.
            count = os.write(self._fds["stdin"], data)
            if count != len(data):
                raise OSError("partial_pipe_write")
            return True
        except Exception as error:
            self._fail("write_failed: %s" % error)
            return False

    def _drain_stdout(self):
        for unused in range(self.MAX_READS_PER_POLL):
            try:
                chunk = os.read(self._fds["stdout"], 4096)
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise
            if not chunk:
                self._fail("worker_output_closed")
                return
            self._stdout_buffer += chunk
            while b"\n" in self._stdout_buffer:
                line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
                if not line or len(line) + 1 > self.MAX_LINE_BYTES:
                    self._fail("invalid_worker_message_size")
                    return
                try:
                    message = json.loads(line.decode("utf-8"))
                    self._receive_message(message)
                except Exception as error:
                    self._fail("invalid_worker_message: %s" % error)
                if self._failed:
                    return
            if len(self._stdout_buffer) >= self.MAX_LINE_BYTES:
                self._fail("invalid_worker_message_size")
                return

    def _drain_stderr(self):
        for unused in range(self.MAX_READS_PER_POLL):
            try:
                chunk = os.read(self._fds["stderr"], 1024)
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                raise
            if not chunk:
                return
            self._stderr_tail = (self._stderr_tail + chunk)[-2048:]

    def _receive_message(self, message):
        if not isinstance(message, dict):
            raise ValueError("message_is_not_an_object")
        kind = message.get("type")
        if kind == "ready":
            if self._ready:
                raise ValueError("duplicate_ready")
            if (message.get("protocol") != 1 or message.get("pid") != self._pid
                    or message.get("events_valid") is not True
                    or message.get("diagnostic") is not self._diagnostic):
                raise ValueError("worker_handshake_mismatch")
            self._ready = True
            self._apply_state(message)
            self._last_status_at = self._clock()
            self._logger.info("LCXL3 keyboard navigation: worker_ready")
        elif kind == "state":
            if not self._ready:
                raise ValueError("state_before_ready")
            self._apply_state(message)
            self._status_pending_at = None
        elif kind == "result":
            if not self._ready:
                raise ValueError("result_before_ready")
            pending = self._pending_press
            if (pending is None or message.get("seq") != pending[0]
                    or message.get("generation") != pending[1]
                    or message.get("status") not in self.RESULT_STATUSES):
                raise ValueError("unexpected_key_acknowledgement")
            self._pending_press = None
            if "frontmost" in message:
                self._apply_state(message)
            elif "focus_epoch" in message:
                epoch = message["focus_epoch"]
                if (type(epoch) is not int or epoch < 0
                        or epoch < self._worker_focus_epoch):
                    raise ValueError("invalid_result_focus_epoch")
                if epoch != self._worker_focus_epoch:
                    self._worker_focus_epoch = epoch
                    self._focus_epoch += 1
                    self._last_state_at = None
                    self._update_effective_frontmost(self._clock())
            if message["status"] in ("invalid", "error"):
                self._fail("worker_key_error: %s: %s" % (
                    message["status"], message.get("detail", "no detail")))
            elif message["status"] == "permission_denied":
                self._allowed = False
                self._update_effective_frontmost(self._clock())
                self._log_permission()
            elif message["status"] == "background":
                self._frontmost = False
                self._update_effective_frontmost(self._clock())
        else:
            raise ValueError("unknown_message_type")

    def _apply_state(self, message):
        frontmost = message.get("frontmost")
        allowed = message.get("allowed")
        epoch = message.get("focus_epoch")
        worker_now = message.get("now")
        if (type(frontmost) is not bool or type(allowed) is not bool
                or type(epoch) is not int or epoch < 0
                or type(worker_now) not in (int, float) or not math.isfinite(worker_now)):
            raise ValueError("invalid_state")
        now = self._clock()
        if abs(now - worker_now) > 1.0:
            raise ValueError("clock_mismatch_or_stale_state")
        if "pid" in message and message["pid"] != self._pid:
            raise ValueError("target_pid_mismatch")
        if "protocol" in message and message["protocol"] != 1:
            raise ValueError("protocol_mismatch")
        if self._worker_focus_epoch is not None and epoch < self._worker_focus_epoch:
            raise ValueError("focus_epoch_moved_backwards")
        if epoch != self._worker_focus_epoch or allowed != self._allowed:
            self._focus_epoch += 1
        if frontmost != self._frontmost:
            self._logger.info("LCXL3 keyboard navigation: Live_%s",
                              "foreground" if frontmost else "background")
        self._frontmost = frontmost
        self._allowed = allowed
        self._worker_focus_epoch = epoch
        # The worker timestamp prevents buffered old state from looking fresh.
        self._last_state_at = min(now, worker_now)
        self._update_effective_frontmost(now)
        if not allowed:
            self._log_permission()

    def _log_permission(self):
        if not self._permission_logged:
            self._permission_logged = True
            self._logger.warning("LCXL3 keyboard navigation: accessibility_permission_required")

    def _update_effective_frontmost(self, now):
        effective = (self._ready and not self._failed and not self._closed
                     and self._frontmost and self._allowed
                     and self._last_state_at is not None
                     and now - self._last_state_at <= self.STATE_MAX_AGE)
        if effective != self._effective_frontmost:
            self._effective_frontmost = effective
            self._focus_epoch += 1

    def _fail(self, reason):
        if self._failed or self._closed:
            return
        self._failed = True
        detail = self._stderr_tail.decode("utf-8", "replace").strip()
        if detail:
            reason += "; stderr: " + detail
        self._logger.warning("LCXL3 keyboard navigation: %s", reason)
        self._ready = False
        self._update_effective_frontmost(self._clock())
        self._dispose_process()

    def close(self):
        if self._closed:
            return
        if self._process is not None and not self._failed:
            self._write_message({"type": "stop"})
        self._closed = True
        self._ready = False
        self._generation += 1
        self._pending_press = None
        self._update_effective_frontmost(self._clock())
        self._dispose_process()

    disconnect = close

    def _dispose_process(self):
        self._process = None
        for name, fd in self._fds.items():
            if name == "stdin" or not self._reaper_started:
                self._close_fd(fd)
            else:
                # Keep response readers open until the child has exited so
                # its last reply cannot cause SIGPIPE during a key pair.
                self._reaper_context["fds"].append(fd)
        self._fds.clear()
        if self._reaper_event is not None:
            self._reaper_event.set()

    @staticmethod
    def _await_cleanup(event, context, timeout_exception):
        event.wait()
        process = context["process"]
        try:
            if process is not None:
                JxaKeyboardSender._reap_process(process, timeout_exception)
        finally:
            for fd in context["fds"]:
                JxaKeyboardSender._close_fd(fd)

    @staticmethod
    def _reap_process(process, timeout_exception):
        try:
            # Allow EOF/stop to finish an already-started keydown/keyup pair
            # before resorting to signals. Every wait is off Live's callbacks.
            try:
                process.wait(timeout=0.2)
            except timeout_exception:
                process.terminate()
                try:
                    process.wait(timeout=0.2)
                except timeout_exception:
                    process.kill()
                    process.wait()
        except (OSError, ProcessLookupError):
            # Popen.poll()/wait() already reap an exited child.
            process.poll()

    @staticmethod
    def _close_fd(fd):
        try:
            os.close(fd)
        except OSError:
            pass
