import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading
import unittest
from unittest import mock


MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "Launch_Control_XL_3_Mixing" / "jxa_keyboard.py")
SPEC = importlib.util.spec_from_file_location("lcxl3_jxa_keyboard_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeClock:
    def __init__(self):
        self.now = 5000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeWorker:
    """An OS-pipe peer, without a subprocess or any native key events."""
    def __init__(self, arguments, **kwargs):
        self.arguments = arguments
        self.options = kwargs
        self.input = os.dup(kwargs["stdin"])
        self.output = os.dup(kwargs["stdout"])
        self.error = os.dup(kwargs["stderr"])
        self.returncode = None
        self.reaped = threading.Event()
        self.terminated = False
        self.killed = False
        self.stubborn = False
        self._read_buffer = b""
        self._closed = False

    def emit(self, message):
        os.write(self.output, (json.dumps(message) + "\n").encode("utf-8"))

    def commands(self):
        while True:
            try:
                chunk = os.read(self.input, 8192)
            except BlockingIOError:
                break
            if not chunk:
                break
            self._read_buffer += chunk
        messages = []
        while b"\n" in self._read_buffer:
            line, self._read_buffer = self._read_buffer.split(b"\n", 1)
            messages.append(json.loads(line))
        return messages

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.returncode = -15
            self.close_pipes()

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.close_pipes()

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.arguments, timeout)
        self.reaped.set()
        return self.returncode

    def close_pipes(self):
        if not self._closed:
            self._closed = True
            for fd in (self.input, self.output, self.error):
                os.close(fd)


class JxaKeyboardSenderTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.workers = []
        self.log = mock.Mock()

        def factory(*args, **kwargs):
            worker = FakeWorker(*args, **kwargs)
            self.workers.append(worker)
            return worker

        self.sender = MODULE.JxaKeyboardSender(
            process_factory=factory, clock=self.clock, platform="darwin",
            pid=1234, log=self.log)

    def tearDown(self):
        self.sender.close()
        for worker in self.workers:
            self.assertTrue(worker.reaped.wait(1), "child must be reaped")
            worker.close_pipes()

    @property
    def worker(self):
        return self.workers[-1]

    def state(self, frontmost=True, allowed=True, epoch=0, **extra):
        message = {"type": "state", "frontmost": frontmost,
                   "allowed": allowed, "focus_epoch": epoch,
                   "now": self.clock()}
        message.update(extra)
        return message

    def ready(self, frontmost=True, allowed=True, **extra):
        self.sender.start()
        message = self.state(frontmost, allowed, type="ready", protocol=1,
                             pid=1234, events_valid=True, diagnostic=False)
        message.update(extra)
        self.worker.emit(message)
        self.sender.poll()

    def reply(self, status="posted", **extra):
        seq, generation, unused = self.sender._pending_press
        message = {"type": "result", "seq": seq,
                   "generation": generation, "status": status}
        message.update(extra)
        self.worker.emit(message)
        self.sender.poll()

    def test_start_is_explicit_once_and_all_pipe_ends_are_nonblocking(self):
        self.assertFalse(self.sender.is_frontmost())
        self.assertEqual(self.workers, [])
        self.assertTrue(self.sender.start())
        self.assertTrue(self.sender.start())
        self.assertEqual(len(self.workers), 1)
        self.assertEqual(self.worker.arguments[:3],
                         ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertTrue(self.worker.arguments[3].endswith("keyboard_worker.js"))
        self.assertEqual(self.worker.arguments[4:], ["1234"])
        self.assertIs(self.worker.options["shell"], False)
        for fd in list(self.sender._fds.values()) + [
                self.worker.input, self.worker.output, self.worker.error]:
            self.assertFalse(os.get_blocking(fd))
        self.assertFalse(self.sender.press(1))

    def test_unsupported_platform_does_not_spawn(self):
        self.sender._platform = "linux"
        self.assertFalse(self.sender.start())
        self.assertFalse(self.sender.start())
        self.assertEqual(self.workers, [])
        self.log.warning.assert_called_once()

    def test_spawn_failure_closes_pipes_and_disables_only_sender(self):
        self.sender._process_factory = mock.Mock(side_effect=OSError("no subprocess"))
        self.assertFalse(self.sender.start())
        self.assertEqual(self.sender._fds, {})
        self.assertFalse(self.sender.press(1))
        self.log.warning.assert_called_once()

    def test_permission_gate_recovers_without_restarting_or_log_flood(self):
        self.ready(allowed=False)
        self.assertFalse(self.sender.press(1))
        self.worker.emit(self.state(allowed=False))
        self.sender.poll()
        self.log.warning.assert_called_once()
        self.worker.emit(self.state(allowed=True, epoch=1))
        self.assertTrue(self.sender.is_frontmost())
        self.assertTrue(self.sender.press(1))
        self.assertEqual(len(self.workers), 1)

    def test_background_and_stale_state_block_keys(self):
        self.ready(frontmost=False)
        self.assertFalse(self.sender.press(-1))
        self.worker.emit(self.state(frontmost=True, epoch=1))
        self.assertTrue(self.sender.is_frontmost())
        self.clock.advance(0.26)
        self.assertFalse(self.sender.press(-1))
        self.assertEqual(self.worker.commands(), [{"type": "status"}])
        self.worker.emit(self.state(frontmost=True, epoch=1))
        self.assertTrue(self.sender.press(-1))

    def test_out_and_back_focus_change_increments_epoch(self):
        self.ready()
        epoch = self.sender.focus_epoch
        self.worker.emit(self.state(epoch=2))
        self.assertTrue(self.sender.is_frontmost())
        self.assertGreater(self.sender.focus_epoch, epoch)
        self.sender.press(-1)
        self.assertEqual(self.worker.commands()[-1]["focus_epoch"], 2)

    def test_only_one_inflight_press_and_no_deferred_repeat(self):
        self.ready()
        self.assertTrue(self.sender.press(-1))
        for unused in range(25):
            self.assertFalse(self.sender.press(1))
        messages = self.worker.commands()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0], {
            "type": "press", "seq": 1, "generation": 0,
            "at": self.clock(), "direction": -1, "focus_epoch": 0})
        self.reply()
        self.assertEqual(self.worker.commands(), [])
        self.assertTrue(self.sender.press(1))
        self.assertEqual(self.worker.commands()[0]["seq"], 2)

    def test_invalid_directions_never_send(self):
        self.ready()
        for direction in (0, 2, None, True, -1.0, "1"):
            self.assertFalse(self.sender.press(direction))
        self.assertEqual(self.worker.commands(), [])

    def test_input_that_expires_during_poll_is_not_written(self):
        self.ready()
        original_poll = self.sender.poll

        def slow_poll():
            original_poll()
            self.clock.advance(0.051)

        with mock.patch.object(self.sender, "poll", side_effect=slow_poll):
            self.assertFalse(self.sender.press(1))
        self.assertEqual(self.worker.commands(), [])

    def test_timestamp_from_input_callback_is_preserved_in_command_and_pending(self):
        self.ready()
        received_at = self.clock()
        self.clock.advance(0.025)
        self.assertTrue(self.sender.press(1, at=received_at))
        self.assertEqual(self.worker.commands()[0]["at"], received_at)
        self.assertEqual(self.sender._pending_press[2], received_at)

    def test_input_already_expired_before_sender_call_is_rejected_without_poll(self):
        self.ready()
        received_at = self.clock()
        self.clock.advance(0.1)
        with mock.patch.object(self.sender, "poll") as poll:
            self.assertFalse(self.sender.press(1, at=received_at))
            poll.assert_not_called()
        self.assertEqual(self.worker.commands(), [])

    def test_passed_timestamp_is_not_refreshed_when_poll_pushes_input_past_deadline(self):
        self.ready()
        received_at = self.clock()
        self.clock.advance(0.03)
        original_poll = self.sender.poll

        def slow_poll():
            original_poll()
            self.clock.advance(0.03)

        with mock.patch.object(self.sender, "poll", side_effect=slow_poll):
            self.assertFalse(self.sender.press(1, at=received_at))
        self.assertEqual(self.worker.commands(), [])

    def test_invalid_input_timestamps_are_rejected(self):
        self.ready()
        for received_at in (True, "5000", float("nan"), float("inf"), -float("inf")):
            self.assertFalse(self.sender.press(1, at=received_at))
        self.assertEqual(self.worker.commands(), [])

    def test_cancel_changes_generation_but_does_not_free_inflight_slot(self):
        self.ready()
        self.assertTrue(self.sender.press(-1))
        self.sender.cancel()
        self.assertFalse(self.sender.press(1))
        commands = self.worker.commands()
        self.assertEqual(commands[-1], {"type": "cancel", "generation": 1})
        self.reply("cancelled")
        self.assertTrue(self.sender.press(1))
        self.assertEqual(self.worker.commands()[-1]["generation"], 1)

    def test_cancel_before_startup_or_without_input_does_not_change_generation(self):
        self.sender.cancel()
        self.sender.start()
        self.sender.cancel()
        self.ready()
        self.assertTrue(self.sender.press(1))
        commands = self.worker.commands()
        self.assertEqual([item["type"] for item in commands], ["press"])
        self.assertEqual(commands[0]["generation"], 0)

    def test_repeated_cancel_does_not_queue_redundant_commands(self):
        self.ready()
        self.sender.press(-1)
        self.sender.cancel()
        self.sender.cancel()
        self.sender.cancel()
        self.assertEqual([item["type"] for item in self.worker.commands()],
                         ["press", "cancel"])

    def test_reaper_thread_failure_happens_before_process_creation(self):
        with mock.patch("threading.Thread.start", side_effect=RuntimeError("thread unavailable")):
            self.assertFalse(self.sender.start())
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.workers, [])
        self.log.warning.assert_called_once()

    def test_busy_expired_result_is_dropped_and_future_input_can_send(self):
        self.ready()
        self.assertTrue(self.sender.press(1))
        self.reply("expired")
        self.assertTrue(self.sender.press(-1))

    def test_result_focus_change_blocks_until_fresh_full_state_arrives(self):
        self.ready()
        self.sender.press(1)
        previous = self.sender.focus_epoch
        self.reply("cancelled", focus_epoch=2)
        self.assertGreater(self.sender.focus_epoch, previous)
        self.assertFalse(self.sender.press(-1))
        self.worker.emit(self.state(epoch=2))
        self.assertTrue(self.sender.press(-1))

    def test_status_has_only_one_outstanding_request(self):
        self.ready()
        self.clock.advance(0.11)
        self.sender.poll()
        self.clock.advance(0.11)
        self.sender.poll()
        self.assertEqual(self.worker.commands(), [{"type": "status"}])
        self.worker.emit(self.state())
        self.sender.poll()
        self.assertEqual(self.worker.commands(), [{"type": "status"}])

    def test_startup_timeout_and_no_automatic_respawn(self):
        self.sender.start()
        self.clock.advance(3.0)
        self.sender.poll()
        self.assertFalse(self.sender.start())
        self.assertFalse(self.sender.press(1))
        self.assertEqual(len(self.workers), 1)
        self.log.warning.assert_called_once()

    def test_key_ack_timeout_stops_worker(self):
        self.ready()
        self.sender.press(1)
        self.clock.advance(0.501)
        self.sender.poll()
        self.assertTrue(self.sender._failed)
        self.assertIn("key_acknowledgement_timeout", self.log.warning.call_args.args[1])

    def test_status_timeout_stops_worker(self):
        self.ready()
        self.clock.advance(0.11)
        self.sender.poll()
        self.clock.advance(0.501)
        self.sender.poll()
        self.assertTrue(self.sender._failed)
        self.assertIn("status_timeout", self.log.warning.call_args.args[1])

    def test_bad_handshake_stops_worker(self):
        self.ready(pid=4321)
        self.assertTrue(self.sender._failed)
        self.assertFalse(self.sender.press(1))

    def test_future_clock_mismatch_stops_worker(self):
        self.ready(now=self.clock() + 2.0)
        self.assertTrue(self.sender._failed)

    def test_ready_delayed_by_live_startup_requests_fresh_state_and_recovers(self):
        self.sender.start()
        worker_at = self.clock()
        self.clock.advance(2.0)
        self.ready(now=worker_at)
        self.assertTrue(self.sender._ready)
        self.assertFalse(self.sender._failed)
        self.assertEqual(self.sender._last_state_at, worker_at)
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.worker.commands(), [{"type": "status"}])
        self.worker.emit(self.state())
        self.assertTrue(self.sender.press(1))
        self.assertEqual(self.worker.commands()[0]["type"], "press")
        self.assertEqual(len(self.workers), 1)

    def test_delayed_result_does_not_refresh_old_state_or_disable_sender(self):
        self.ready()
        self.assertTrue(self.sender.press(1))
        self.worker.commands()
        worker_at = self.clock()
        self.clock.advance(2.0)
        self.reply("posted", frontmost=True, allowed=True,
                   focus_epoch=0, now=worker_at)
        self.assertFalse(self.sender._failed)
        self.assertIsNone(self.sender._pending_press)
        self.assertEqual(self.sender._last_state_at, worker_at)
        self.assertFalse(self.sender.press(-1))
        self.assertEqual(self.worker.commands(), [{"type": "status"}])
        self.worker.emit(self.state())
        self.assertTrue(self.sender.press(-1))

    def test_fragmented_worker_line_waits_for_newline(self):
        self.sender.start()
        message = self.state(type="ready", protocol=1, pid=1234,
                             events_valid=True, diagnostic=False)
        encoded = (json.dumps(message) + "\n").encode("utf-8")
        os.write(self.worker.output, encoded[:20])
        self.sender.poll()
        self.assertFalse(self.sender._ready)
        os.write(self.worker.output, encoded[20:])
        self.assertTrue(self.sender.is_frontmost())

    def test_oversized_worker_line_stops_worker(self):
        self.ready()
        os.write(self.worker.output, b"x" * 1024)
        self.sender.poll()
        self.assertTrue(self.sender._failed)

    def test_eof_stops_worker(self):
        self.ready()
        os.close(self.worker.output)
        self.worker.output = os.open(os.devnull, os.O_WRONLY)
        self.sender.poll()
        self.assertTrue(self.sender._failed)

    def test_unexpected_ack_stops_worker(self):
        self.ready()
        self.worker.emit({"type": "result", "seq": 123,
                          "generation": 0, "status": "posted"})
        self.sender.poll()
        self.assertTrue(self.sender._failed)

    def test_pipe_full_and_partial_write_are_fail_closed(self):
        self.ready()
        with mock.patch.object(MODULE.os, "write", side_effect=BlockingIOError(errno.EAGAIN, "full")):
            self.assertFalse(self.sender.press(1))
        self.assertTrue(self.sender._failed)

    def test_partial_write_is_fail_closed(self):
        self.ready()
        with mock.patch.object(MODULE.os, "write", return_value=3):
            self.assertFalse(self.sender.press(-1))
        self.assertTrue(self.sender._failed)

    def test_stderr_is_drained_with_a_bounded_tail(self):
        self.ready()
        os.write(self.worker.error, b"e" * 4000)
        self.sender.poll()
        self.assertEqual(len(self.sender._stderr_tail), 2048)
        self.assertTrue(self.sender.is_frontmost())
        self.worker.emit({"type": "invalid"})
        self.sender.poll()
        self.assertIn("stderr: ", self.log.warning.call_args.args[1])

    def test_permission_denied_result_immediately_blocks_following_input(self):
        self.ready()
        self.sender.press(1)
        self.reply("permission_denied")
        self.assertFalse(self.sender.press(1))

    def test_close_terminates_and_reaps_a_stubborn_child_off_callback_thread(self):
        self.ready()
        self.worker.stubborn = True
        calling_thread = threading.get_ident()
        original_wait = self.worker.wait
        wait_threads = []

        def checked_wait(timeout=None):
            wait_threads.append(threading.get_ident())
            return original_wait(timeout)

        self.worker.wait = checked_wait
        self.sender.close()
        self.sender.close()
        self.assertTrue(self.worker.reaped.wait(1))
        self.assertTrue(self.worker.terminated)
        self.assertTrue(self.worker.killed)
        self.assertTrue(all(item != calling_thread for item in wait_threads))
        self.assertFalse(self.sender.start())
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.sender._fds, {})

    def test_diagnostic_mode_is_explicit_in_arguments_and_handshake(self):
        self.sender._diagnostic = True
        self.ready(diagnostic=True)
        self.assertEqual(self.worker.arguments[-1], "--diagnostic")
        self.assertTrue(self.sender.press(1))
        self.reply("diagnostic")


if __name__ == "__main__":
    unittest.main()
