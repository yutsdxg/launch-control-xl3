"""Send plain arrow-key presses through macOS, without external processes."""

import logging
import os
import sys

LOGGER = logging.getLogger(__name__)
UP_ARROW_KEYCODE = 126
DOWN_ARROW_KEYCODE = 125


class _NativeBindings:
    def __init__(self):
        # Avoid relying on Live shipping the Python ctypes package.
        import _ctypes

        class Pointer(_ctypes._SimpleCData):
            _type_ = "P"

        class CString(_ctypes._SimpleCData):
            _type_ = "z"

        class Integer(_ctypes._SimpleCData):
            _type_ = "i"

        class KeyCode(_ctypes._SimpleCData):
            _type_ = "H"

        class Boolean(_ctypes._SimpleCData):
            _type_ = "?"

        class EventFlags(_ctypes._SimpleCData):
            _type_ = "Q"

        type_sizes = tuple(_ctypes.sizeof(kind) for kind in (Pointer, Integer, KeyCode, Boolean, EventFlags))
        if type_sizes != (8, 4, 2, 1, 8):
            raise RuntimeError("unsupported macOS native type sizes")

        def bind(handle, name, result, arguments):
            class Function(_ctypes.CFuncPtr):
                _flags_ = _ctypes.FUNCFLAG_CDECL
                _restype_ = result
                _argtypes_ = arguments

            return Function(_ctypes.dlsym(handle, name))

        core_graphics = _ctypes.dlopen("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        core_foundation = _ctypes.dlopen("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        objc = _ctypes.dlopen("/usr/lib/libobjc.A.dylib")
        appkit = _ctypes.dlopen("/System/Library/Frameworks/AppKit.framework/AppKit")
        self._handles = (core_graphics, core_foundation, objc, appkit)

        self.can_post = bind(core_graphics, "CGPreflightPostEventAccess", Boolean, ())
        self._create_event = bind(core_graphics, "CGEventCreateKeyboardEvent", Pointer,
                                  (Pointer, KeyCode, Boolean))
        self.set_flags = bind(core_graphics, "CGEventSetFlags", None, (Pointer, EventFlags))
        self.post = bind(core_graphics, "CGEventPostToPid", None, (Integer, Pointer))
        self.release = bind(core_foundation, "CFRelease", None, (Pointer,))

        get_class = bind(objc, "objc_getClass", Pointer, (CString,))
        selector = bind(objc, "sel_registerName", Pointer, (CString,))
        # objc_msgSend must have the exact return type of each target method.
        self._send_object = bind(objc, "objc_msgSend", Pointer, (Pointer, Pointer))
        self._send_integer = bind(objc, "objc_msgSend", Integer, (Pointer, Pointer))
        self._send_void = bind(objc, "objc_msgSend", None, (Pointer, Pointer))
        self._workspace_class = get_class(b"NSWorkspace")
        self._pool_class = get_class(b"NSAutoreleasePool")
        if not self._workspace_class or not self._pool_class:
            raise RuntimeError("macOS workspace classes unavailable")
        self._selectors = {
            name: selector(name.encode("ascii"))
            for name in ("sharedWorkspace", "frontmostApplication", "processIdentifier", "alloc", "init", "drain")
        }
        if not all(self._selectors.values()):
            raise RuntimeError("macOS workspace selectors unavailable")

    def is_frontmost(self, pid):
        selectors = self._selectors
        pool = self._send_object(self._pool_class, selectors["alloc"])
        pool = self._send_object(pool, selectors["init"]) if pool else None
        if not pool:
            raise RuntimeError("macOS autorelease pool unavailable")
        try:
            workspace = self._send_object(self._workspace_class, selectors["sharedWorkspace"])
            if not workspace:
                return False
            application = self._send_object(workspace, selectors["frontmostApplication"])
            return bool(application) and self._send_integer(application, selectors["processIdentifier"]) == pid
        finally:
            self._send_void(pool, selectors["drain"])

    def create_keyboard_event(self, keycode, key_down):
        return self._create_event(None, keycode, key_down)


class MacKeyboardSender:
    """Lazy, failure-isolated native sender; direction -1 is Up, +1 is Down."""

    def __init__(self):
        self._bindings = None
        self._initialization_attempted = False
        self._state = None

    def _set_state(self, state, detail=None):
        if state == self._state:
            return
        self._state = state
        log = LOGGER.info if state == "ready" else LOGGER.warning
        log("LCXL3 keyboard navigation: %s%s", state, ": {}".format(detail) if detail else "")

    def _native(self):
        if not self._initialization_attempted:
            self._initialization_attempted = True
            if sys.platform != "darwin":
                self._set_state("unsupported_platform")
            else:
                try:
                    self._bindings = _NativeBindings()
                except Exception as error:
                    self._set_state("initialization_failed", error)
        return self._bindings

    def is_frontmost(self):
        native = self._native()
        if native is None:
            return False
        try:
            return bool(native.is_frontmost(os.getpid()))
        except Exception as error:
            self._set_state("focus_check_failed", error)
            return False

    def _allowed_to_post(self, native, pid):
        if not native.is_frontmost(pid):
            return False
        if not native.can_post():
            self._set_state("accessibility_permission_required")
            return False
        return True

    def press(self, direction):
        if direction not in (-1, 1):
            return False
        native = self._native()
        if native is None:
            return False
        pid = os.getpid()
        keycode = UP_ARROW_KEYCODE if direction < 0 else DOWN_ARROW_KEYCODE
        events = []
        success = False
        down_posted = False
        try:
            if not self._allowed_to_post(native, pid):
                return False
            for key_down in (True, False):
                event = native.create_keyboard_event(keycode, key_down)
                if not event:
                    self._set_state("event_creation_failed")
                    return False
                events.append(event)
                native.set_flags(event, 0)
            # Focus can change during event creation. Never queue a later press.
            if not self._allowed_to_post(native, pid):
                return False
            down_posted = True
            native.post(pid, events[0])
            native.post(pid, events[1])
            down_posted = False
            success = True
        except Exception as error:
            self._set_state("native_send_failed", error)
            if down_posted:
                try:
                    native.post(pid, events[1])
                except Exception:
                    pass
        finally:
            for event in events:
                try:
                    native.release(event)
                except Exception as error:
                    success = False
                    self._set_state("event_cleanup_failed", error)
        if success:
            self._set_state("ready")
        return success
