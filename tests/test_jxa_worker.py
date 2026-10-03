"""Exercise the actual JXA protocol without sending any real keyboard events."""

import json
import os
import select
import subprocess
import sys
import time
import unittest
from pathlib import Path


WORKER = Path(__file__).resolve().parents[1] / "Launch_Control_XL_3_Mixing" / "keyboard_worker.js"
OSASCRIPT = "/usr/bin/osascript"
HAS_JXA = sys.platform == "darwin" and Path(OSASCRIPT).exists()

FAKE_NATIVE = """
var output = [], events = [], posts = [], released = [], flags = [];
var clock = 10, focus = 4, frontmost = true, allowed = true;
var afterCreate = function () {}, afterPost = function () {};
var failSecondCreate = false;
var native = {
    now: function () { return clock; },
    state: function () { return {frontmost:frontmost, allowed:allowed, focus_epoch:focus}; },
    create: function (key, down) {
        if (failSecondCreate && !down) { return null; }
        var event = {id:events.length, key:key, down:down};
        events.push(event); afterCreate(event); return event;
    },
    flags: function (event, value) { flags.push([event.id, value]); },
    post: function (pid, event) { posts.push([pid,event.key,event.down]); afterPost(event); },
    release: function (event) { released.push(event.id); },
    validateEvents: function () { return true; }
};
function command(seq, changes) {
    var value = {type:'press',seq:seq,generation:0,at:10,direction:-1,focus_epoch:4};
    Object.keys(changes || {}).forEach(function(key) { value[key] = changes[key]; });
    return value;
}
function protocol(diagnostic) {
    return createKeyboardProtocol(native, function(value) { output.push(value); }, 42, diagnostic);
}
"""


@unittest.skipUnless(HAS_JXA, "macOS JavaScript for Automation is required")
class JxaProtocolTests(unittest.TestCase):
    def execute(self, test):
        source = WORKER.read_text() + "\nfunction run() {\n" + FAKE_NATIVE + test + "\n}"
        result = subprocess.run(
            [OSASCRIPT, "-l", "JavaScript", "-e", source],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_up_down_repeat_have_exact_pair_flags_and_release(self):
        value = self.execute("""
var p = protocol(false);
p.batch([command(1)]); p.batch([command(2,{direction:1})]); p.batch([command(3,{direction:1})]);
return JSON.stringify({posts:posts,flags:flags,released:released,output:output});
""")
        self.assertEqual(value["posts"], [[42, 126, True], [42, 126, False],
                                         [42, 125, True], [42, 125, False],
                                         [42, 125, True], [42, 125, False]])
        self.assertEqual(value["flags"], [[i, 0] for i in range(6)])
        self.assertEqual(sorted(value["released"]), list(range(6)))
        self.assertEqual([item["status"] for item in value["output"]], ["posted"] * 3)

    def test_down_failure_still_attempts_up_to_same_pid(self):
        value = self.execute("""
afterPost = function(event) { frontmost = false; if(event.down) { throw new Error('down_failed'); } };
protocol(false).batch([command(1)]);
return JSON.stringify({posts:posts,released:released,output:output});
""")
        self.assertEqual(value["posts"], [[42, 126, True], [42, 126, False]])
        self.assertEqual(sorted(value["released"]), [0, 1])
        self.assertEqual(value["output"][0]["status"], "error")

    def test_second_creation_failure_never_posts_half_pair(self):
        value = self.execute("""
failSecondCreate = true; protocol(false).batch([command(1)]);
return JSON.stringify({posts:posts,released:released,output:output});
""")
        self.assertEqual(value["posts"], [])
        self.assertEqual(value["released"], [0])
        self.assertEqual(value["output"][0]["status"], "error")

    def test_expiry_and_focus_are_rechecked_after_event_creation(self):
        for change, status in (("clock += 0.03;", "expired"),
                               ("frontmost = false;", "background"),
                               ("focus += 1;", "cancelled"),
                               ("allowed = false;", "permission_denied")):
            with self.subTest(status=status):
                value = self.execute("""
afterCreate = function(event) { %s };
protocol(false).batch([command(1)]);
return JSON.stringify({posts:posts,released:released,output:output});
""" % change)
                self.assertEqual(value["posts"], [])
                self.assertEqual(sorted(value["released"]), [0, 1])
                self.assertEqual(value["output"][0]["status"], status)

    def test_stale_future_invalid_and_background_inputs_never_create_events(self):
        value = self.execute("""
var p = protocol(false);
p.batch([command(1,{at:9})]); p.batch([command(2,{at:11})]);
p.batch([command(3,{direction:0})]); p.batch([command(4,{focus_epoch:3})]);
frontmost = false; p.batch([command(5)]);
frontmost = true; allowed = false; p.batch([command(6)]);
return JSON.stringify({events:events,output:output});
""")
        self.assertEqual(value["events"], [])
        self.assertEqual([v["status"] for v in value["output"]],
                         ["expired", "invalid", "invalid", "cancelled", "background", "permission_denied"])

    def test_later_cancel_in_batch_invalidates_earlier_press(self):
        value = self.execute("""
var p = protocol(false);
p.batch([command(1),{type:'cancel',generation:1}]);
p.batch([command(2,{generation:1})]);
return JSON.stringify({posts:posts,output:output});
""")
        self.assertEqual([v["status"] for v in value["output"]], ["cancelled", "posted"])
        self.assertEqual(len(value["posts"]), 2)

    def test_burst_has_at_most_one_pair_and_stop_discards_batch(self):
        value = self.execute("""
var p = protocol(false);
p.batch([command(1),command(2),command(3)]);
var running = p.batch([command(4),{type:'stop'}]);
return JSON.stringify({running:running,posts:posts,output:output});
""")
        self.assertFalse(value["running"])
        self.assertEqual(len(value["posts"]), 2)
        self.assertEqual([v["status"] for v in value["output"]], ["cancelled", "cancelled", "posted"])

    def test_diagnostic_constructs_events_without_posting(self):
        value = self.execute("""
var p = protocol(true); p.ready(); p.batch([command(1)]);
return JSON.stringify({events:events,posts:posts,released:released,output:output});
""")
        self.assertEqual(len(value["events"]), 2)
        self.assertEqual(value["posts"], [])
        self.assertEqual(sorted(value["released"]), [0, 1])
        self.assertTrue(value["output"][0]["events_valid"])
        self.assertEqual(value["output"][1]["status"], "diagnostic")


@unittest.skipUnless(HAS_JXA, "macOS JavaScript for Automation is required")
class JxaNativeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        # Every real subprocess is unconditionally diagnostic. No test posts keys.
        read_fd, self.write_fd = os.pipe()
        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        for fd in (read_fd, self.write_fd, stdout_read, stdout_write, stderr_read, stderr_write):
            os.set_blocking(fd, False)
        self.process = subprocess.Popen(
            [OSASCRIPT, "-l", "JavaScript", str(WORKER), str(os.getpid()), "--diagnostic"],
            stdin=read_fd, stdout=stdout_write, stderr=stderr_write,
        )
        for fd in (read_fd, stdout_write, stderr_write):
            os.close(fd)
        self.stdout_fd, self.stderr_fd = stdout_read, stderr_read
        self.buffer = b""
        self.errors = b""
        self.messages = []
        self.ready = self.receive("ready")

    def tearDown(self):
        if self.write_fd is not None:
            os.close(self.write_fd)
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        os.close(self.stdout_fd)
        os.close(self.stderr_fd)

    def receive(self, kind, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, value in enumerate(self.messages):
                if value["type"] == kind:
                    return self.messages.pop(index)
            for fd in select.select([self.stdout_fd, self.stderr_fd], [], [], 0.02)[0]:
                data = os.read(fd, 65536)
                if fd == self.stderr_fd:
                    self.errors = (self.errors + data)[-8192:]
                else:
                    self.buffer += data
                    while b"\n" in self.buffer:
                        line, self.buffer = self.buffer.split(b"\n", 1)
                        self.messages.append(json.loads(line))
            if self.process.poll() is not None:
                self.fail("worker exited before %s: %s" % (kind, self.errors.decode(errors="replace")))
        self.fail("timed out waiting for %s: %s" % (kind, self.errors.decode(errors="replace")))

    def send(self, value):
        payload = (json.dumps(value) + "\n").encode()
        self.assertEqual(os.write(self.write_fd, payload), len(payload))

    def test_ready_native_event_creation_and_fragmented_status(self):
        self.assertTrue(self.ready["diagnostic"])
        self.assertTrue(self.ready["events_valid"])
        self.assertEqual(self.ready["protocol"], 1)
        self.assertLess(abs(time.monotonic() - self.ready["now"]), 1)
        os.write(self.write_fd, b'{"type":"sta')
        os.write(self.write_fd, b'tus"}\n')
        value = self.receive("state")
        self.assertIsInstance(value["frontmost"], bool)
        self.assertIsInstance(value["allowed"], bool)
        self.assertIsInstance(value["focus_epoch"], int)

    def test_native_expiry_cancel_and_eof(self):
        base = dict(type="press", seq=1, generation=0, at=self.ready["now"] - 1,
                    direction=-1, focus_epoch=self.ready["focus_epoch"])
        self.send(base)
        self.assertEqual(self.receive("result")["status"], "expired")
        payload = json.dumps(dict(base, seq=2)) + "\n" + json.dumps(dict(type="cancel", generation=1)) + "\n"
        os.write(self.write_fd, payload.encode())
        self.assertEqual(self.receive("result")["status"], "cancelled")
        os.close(self.write_fd)
        self.write_fd = None
        self.assertEqual(self.process.wait(timeout=2), 0)

    def test_oversized_line_fails_closed(self):
        os.write(self.write_fd, b"x" * 1024)
        self.assertNotEqual(self.process.wait(timeout=2), 0)

    def test_stdout_backpressure_exits_without_blocking(self):
        # Stop consuming stdout and fill it with state replies. Requests remain
        # individually below the protocol bound and no press command is used.
        deadline = time.monotonic() + 4
        payload = b'{"type":"status"}\n' * 16
        while self.process.poll() is None and time.monotonic() < deadline:
            try:
                os.write(self.write_fd, payload)
            except (BlockingIOError, BrokenPipeError):
                pass
            time.sleep(0.002)
        self.assertIsNotNone(self.process.poll(), "worker blocked on a nonreading output pipe")
        self.assertNotEqual(self.process.returncode, 0)
        self.errors += os.read(self.stderr_fd, 8192)
        self.assertIn(b"output_unavailable", self.errors)


if __name__ == "__main__":
    unittest.main()
