/* Persistent macOS key sender. Run only through JxaKeyboardSender.
 * --diagnostic constructs and releases events but NEVER posts a key.
 * The protocol core also runs under Node with a fake native adapter in tests.
 */
function createKeyboardProtocol(native, emit, pid, diagnostic) {
    var generation = 0;
    var stopped = false;

    function integer(value) {
        return typeof value === "number" && isFinite(value) &&
            Math.floor(value) === value && value >= 0;
    }

    function state(type) {
        var value = native.state();
        value.type = type;
        value.now = native.now();
        return value;
    }

    function rejection(command) {
        if (!integer(command.seq) || !integer(command.generation) ||
                !integer(command.focus_epoch) ||
                (command.direction !== -1 && command.direction !== 1) ||
                typeof command.at !== "number" || !isFinite(command.at)) {
            return "invalid";
        }
        if (command.generation !== generation) { return "cancelled"; }
        var current = native.state();
        if (command.focus_epoch !== current.focus_epoch) { return "cancelled"; }
        var age = native.now() - command.at;
        if (age < -0.005) { return "invalid"; }
        if (age > 0.05) { return "expired"; }
        if (!current.frontmost) { return "background"; }
        if (!current.allowed) { return "permission_denied"; }
        return null;
    }

    function press(command) {
        var result = {
            type: "result", seq: command.seq, generation: command.generation,
            focus_epoch: native.state().focus_epoch, status: rejection(command)
        };
        var down = null;
        var up = null;
        try {
            if (!result.status) {
                var key = command.direction < 0 ? 126 : 125;
                // Create BOTH events before posting either. All CG ownership is
                // raw void pointers, never automatically managed ObjC wrappers.
                down = native.create(key, true);
                up = native.create(key, false);
                if (!down || !up) { throw new Error("event_creation_failed"); }
                native.flags(down, 0);
                native.flags(up, 0);
                // Event construction can take time; recheck immediately before
                // the pair. Once down starts, up must go to the same PID.
                result.status = rejection(command);
                if (!result.status) {
                    if (diagnostic) {
                        result.status = "diagnostic";
                    } else {
                        try {
                            native.post(pid, down);
                        } finally {
                            native.post(pid, up);
                        }
                        result.status = "posted";
                    }
                }
            }
        } catch (error) {
            result.status = "error";
            result.detail = String(error).slice(0, 160);
        } finally {
            if (up) { native.release(up); }
            if (down) { native.release(down); }
        }
        var finalState = native.state();
        result.focus_epoch = finalState.focus_epoch;
        result.frontmost = finalState.frontmost;
        result.allowed = finalState.allowed;
        result.now = native.now();
        emit(result);
    }

    return {
        ready: function () {
            var value = state("ready");
            value.protocol = 1;
            value.pid = pid;
            value.diagnostic = diagnostic;
            value.events_valid = native.validateEvents();
            emit(value);
        },
        changed: function () { emit(state("state")); },
        batch: function (commands) {
            var lastPress = -1;
            // Cancellation wins over every press already received in this batch.
            commands.forEach(function (command, index) {
                if (command.type === "stop") { stopped = true; }
                if (command.type === "cancel" && integer(command.generation)) {
                    generation = Math.max(generation, command.generation);
                }
                if (command.type === "press") { lastPress = index; }
            });
            if (stopped) { return false; }
            commands.forEach(function (command, index) {
                if (command.type === "status") { emit(state("state")); }
                if (command.type === "press") {
                    if (index === lastPress) {
                        press(command);
                    } else {
                        emit({type: "result", seq: command.seq,
                            generation: command.generation,
                            focus_epoch: native.state().focus_epoch,
                            status: "cancelled"});
                    }
                }
            });
            return true;
        }
    };
}

function run(argv) {
    if (argv.length < 1 || argv.length > 2 || !/^[1-9][0-9]*$/.test(argv[0]) ||
            (argv.length === 2 && argv[1] !== "--diagnostic")) {
        throw new Error("usage: keyboard_worker.js PID [--diagnostic]");
    }
    var pid = Number(argv[0]);
    if (pid > 2147483647) { throw new Error("invalid_pid"); }
    var diagnostic = argv.length === 2;
    ObjC.import("Foundation");
    ObjC.import("AppKit");
    ObjC.import("CoreGraphics");
    // Explicit void-pointer bindings avoid JXA's CF Create-result ownership.
    ObjC.bindFunction("CGEventCreateKeyboardEvent", ["void *", ["void *", "unsigned short", "bool"]]);
    ObjC.bindFunction("CGEventSetFlags", ["void", ["void *", "unsigned long long"]]);
    ObjC.bindFunction("CGEventPostToPid", ["void", ["int", "void *"]]);
    ObjC.bindFunction("CGPreflightPostEventAccess", ["bool", []]);
    ObjC.bindFunction("CFRelease", ["void", ["void *"]]);
    ObjC.bindFunction("poll", ["int", ["void *", "unsigned int", "int"]]);
    ObjC.bindFunction("read", ["long", ["int", "void *", "unsigned long"]]);
    ObjC.bindFunction("write", ["long", ["int", "void *", "unsigned long"]]);

    var workspace = $.NSWorkspace.sharedWorkspace;
    var uptime = $.NSProcessInfo.processInfo;
    var runLoop = $.NSRunLoop.currentRunLoop;
    var nullPointer = $.NSValue.valueWithPointer(null);
    var frontmost = false;
    var focusEpoch = 0;
    var stateChanged = false;
    var input = "";
    var buffer = $.NSMutableData.dataWithLength(4096);
    // struct pollfd { int fd=0; short events=POLLIN; short revents=0; }.
    // Parent sets stdin/stdout/stderr O_NONBLOCK before spawning us. In
    // particular, do not bind variadic fcntl as a fixed-argument C function.
    var pollfd = $.NSMutableData.alloc.initWithBase64EncodedStringOptions("AAAAAAEAAAA=", 0);

    function updateFocus(activePid) {
        var next = activePid === pid;
        if (next !== frontmost) {
            frontmost = next;
            focusEpoch += 1;
            stateChanged = true;
        }
    }
    function refreshFocus() {
        var app = workspace.frontmostApplication;
        updateFocus(app ? Number(app.processIdentifier) : 0);
    }
    refreshFocus();
    var observer = workspace.notificationCenter.addObserverForNameObjectQueueUsingBlock(
        $.NSWorkspaceDidActivateApplicationNotification, null, null,
        function (notification) {
            var app = notification.userInfo.objectForKey($.NSWorkspaceApplicationKey);
            updateFocus(app ? Number(app.processIdentifier) : 0);
        }
    );

    function emit(value) {
        var data = $(JSON.stringify(value) + "\n").dataUsingEncoding($.NSUTF8StringEncoding);
        if (Number(data.length) > 1024 || Number($.write(1, data.bytes, data.length)) !== Number(data.length)) {
            // A full/nonreading pipe is a transport failure, never a key queue.
            throw new Error("output_unavailable");
        }
    }
    var native = {
        now: function () { return Number(uptime.systemUptime); },
        state: function () {
            refreshFocus();
            return {frontmost: frontmost, allowed: Boolean($.CGPreflightPostEventAccess()),
                focus_epoch: focusEpoch};
        },
        create: function (key, down) {
            var event = $.CGEventCreateKeyboardEvent(null, key, down);
            // Ref(NULL) is truthy in JXA; compare boxed pointer values without
            // dereferencing it or introducing a CF-owning ObjC wrapper.
            return $.NSValue.valueWithPointer(event).isEqualToValue(nullPointer) ? null : event;
        },
        flags: function (event, flags) { $.CGEventSetFlags(event, flags); },
        post: function (target, event) { $.CGEventPostToPid(target, event); },
        release: function (event) { $.CFRelease(event); },
        validateEvents: function () {
            [126, 125].forEach(function (key) {
                [true, false].forEach(function (down) {
                    var event = native.create(key, down);
                    if (!event) { throw new Error("event_creation_failed"); }
                    try { native.flags(event, 0); } finally { native.release(event); }
                });
            });
            return true;
        }
    };
    var protocol = createKeyboardProtocol(native, emit, pid, diagnostic);
    try {
        protocol.ready();
        stateChanged = false;
        while (true) {
            // Pump NSWorkspace activation notifications even without MIDI input.
            // Their epoch catches focus leaving and returning between polls.
            runLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.001));
            refreshFocus();
            if (stateChanged) {
                stateChanged = false;
                protocol.changed();
            }
            if ($.poll(pollfd.mutableBytes, 1, 50) <= 0) { continue; }
            var commands = [];
            var eof = false;
            var total = 0;
            do {
                var count = Number($.read(0, buffer.mutableBytes, 4096));
                if (count === 0) { eof = true; break; }
                if (count < 0) { break; }
                total += count;
                if (total > 65536) { throw new Error("input_flood"); }
                var chunk = $.NSString.alloc.initWithDataEncoding(
                    buffer.subdataWithRange($.NSMakeRange(0, count)), $.NSUTF8StringEncoding);
                var decoded = ObjC.unwrap(chunk);
                // Python uses ensure_ascii JSON: reject ambiguous byte/character
                // lengths and partial UTF-8 at the framing boundary.
                if (typeof decoded !== "string" || /[^\x00-\x7f]/.test(decoded)) {
                    throw new Error("invalid_encoding");
                }
                input += decoded;
                var newline;
                while ((newline = input.indexOf("\n")) !== -1) {
                    if (newline > 1023) { throw new Error("input_line_too_long"); }
                    var line = input.slice(0, newline);
                    input = input.slice(newline + 1);
                    var command = JSON.parse(line);
                    if (!command || typeof command !== "object" || Array.isArray(command)) {
                        throw new Error("invalid_command");
                    }
                    commands.push(command);
                }
                if (input.length > 1023) { throw new Error("input_line_too_long"); }
            } while ($.poll(pollfd.mutableBytes, 1, 0) > 0);
            // EOF means the controlling script ended: discard all pending work.
            if (eof) { break; }
            // Drain activation notifications received while poll was asleep.
            runLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.001));
            if (!protocol.batch(commands)) { break; }
        }
    } finally {
        workspace.notificationCenter.removeObserver(observer);
    }
}

if (typeof module !== "undefined") {
    module.exports = {createKeyboardProtocol: createKeyboardProtocol};
}
