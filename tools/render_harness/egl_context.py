"""T-003 — headless EGL/GLES context via EGL_EXT_platform_device.

No `/dev/dri` and no windowing system are available in this environment (see
docs/backlog-status.md's 2026-09-17 update), but Mesa's EGL_EXT_platform_device
path reaches the llvmpipe software rasterizer without either. PyOpenGL's EGL
bindings don't cover the device-enumeration extensions this path needs
(EGL_EXT_device_enumeration / EGL_EXT_platform_device aren't core EGL), so
context creation is done directly via ctypes against libEGL.so.1, then GL
calls after `make_current()` go through PyOpenGL as normal (a made-current
context is all PyOpenGL needs; it doesn't care how it was created).

This intentionally does not use EGL_PLATFORM_SURFACELESS_MESA — that platform
multiplexes onto whatever display backend Mesa would otherwise pick (X11/
Wayland/GBM), none of which exist here. EGL_EXT_platform_device talks to the
software device directly and is what the environment probe confirmed works.
"""
import ctypes

egl = ctypes.CDLL("libEGL.so.1")

EGLint = ctypes.c_int32
EGLBoolean = ctypes.c_uint32
EGLDisplay = ctypes.c_void_p
EGLConfig = ctypes.c_void_p
EGLContext = ctypes.c_void_p
EGLSurface = ctypes.c_void_p
EGLDeviceEXT = ctypes.c_void_p

EGL_PLATFORM_DEVICE_EXT = 0x313F
EGL_NONE = 0x3038
EGL_SURFACE_TYPE = 0x3033
EGL_PBUFFER_BIT = 0x0001
EGL_RENDERABLE_TYPE = 0x3040
EGL_OPENGL_ES3_BIT = 0x0040
EGL_RED_SIZE = 0x3024
EGL_GREEN_SIZE = 0x3023
EGL_BLUE_SIZE = 0x3022
EGL_ALPHA_SIZE = 0x3021
EGL_WIDTH = 0x3057
EGL_HEIGHT = 0x3056
EGL_CONTEXT_CLIENT_VERSION = 0x3098
EGL_OPENGL_ES_API = 0x30A0
EGL_TRUE = 1

egl.eglGetProcAddress.restype = ctypes.c_void_p
egl.eglGetProcAddress.argtypes = [ctypes.c_char_p]


def _proc(name, restype, argtypes):
    addr = egl.eglGetProcAddress(name.encode())
    if not addr:
        raise RuntimeError(f"eglGetProcAddress({name}) returned NULL — extension not present")
    fn = ctypes.CFUNCTYPE(restype, *argtypes)(addr)
    return fn


class HeadlessContext:
    """Creates and owns a single headless GLES3 context + pbuffer surface.

    Use as a context manager so eglTerminate/eglDestroySurface run even if
    shader compilation raises.
    """

    def __init__(self, width: int, height: int, device_index: int = 0):
        self.width = width
        self.height = height
        self.device_index = device_index
        self.display = None
        self.surface = None
        self.context = None

    def __enter__(self):
        eglQueryDevicesEXT = _proc(
            "eglQueryDevicesEXT", EGLBoolean,
            [EGLint, ctypes.POINTER(EGLDeviceEXT), ctypes.POINTER(EGLint)],
        )
        eglGetPlatformDisplayEXT = _proc(
            "eglGetPlatformDisplayEXT", EGLDisplay,
            [EGLint, ctypes.c_void_p, ctypes.POINTER(EGLint)],
        )

        max_devices = 8
        devices = (EGLDeviceEXT * max_devices)()
        num_devices = EGLint(0)
        if not eglQueryDevicesEXT(max_devices, devices, ctypes.byref(num_devices)):
            raise RuntimeError("eglQueryDevicesEXT failed")
        if num_devices.value == 0:
            raise RuntimeError("no EGL devices enumerated")
        if self.device_index >= num_devices.value:
            raise RuntimeError(
                f"device index {self.device_index} out of range "
                f"({num_devices.value} device(s) available)"
            )

        self.display = eglGetPlatformDisplayEXT(
            EGL_PLATFORM_DEVICE_EXT, devices[self.device_index], None
        )
        if not self.display:
            raise RuntimeError("eglGetPlatformDisplayEXT returned no display")

        major, minor = EGLint(0), EGLint(0)
        if not egl.eglInitialize(self.display, ctypes.byref(major), ctypes.byref(minor)):
            raise RuntimeError("eglInitialize failed")

        if not egl.eglBindAPI(EGL_OPENGL_ES_API):
            raise RuntimeError("eglBindAPI(EGL_OPENGL_ES_API) failed")

        config_attribs = (EGLint * 13)(
            EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
            EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT,
            EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
            EGL_NONE,
        )
        config = EGLConfig()
        num_config = EGLint(0)
        if not egl.eglChooseConfig(
            self.display, config_attribs, ctypes.byref(config), 1, ctypes.byref(num_config)
        ):
            raise RuntimeError("eglChooseConfig failed")
        if num_config.value == 0:
            raise RuntimeError("no matching EGL config")

        pbuffer_attribs = (EGLint * 5)(
            EGL_WIDTH, self.width, EGL_HEIGHT, self.height, EGL_NONE
        )
        self.surface = egl.eglCreatePbufferSurface(self.display, config, pbuffer_attribs)
        if not self.surface:
            raise RuntimeError("eglCreatePbufferSurface failed")

        context_attribs = (EGLint * 3)(EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE)
        self.context = egl.eglCreateContext(self.display, config, None, context_attribs)
        if not self.context:
            raise RuntimeError("eglCreateContext failed")

        if not egl.eglMakeCurrent(self.display, self.surface, self.surface, self.context):
            raise RuntimeError("eglMakeCurrent failed")

        return self

    def __exit__(self, exc_type, exc, tb):
        if self.display:
            egl.eglMakeCurrent(self.display, None, None, None)
            if self.context:
                egl.eglDestroyContext(self.display, self.context)
            if self.surface:
                egl.eglDestroySurface(self.display, self.surface)
            egl.eglTerminate(self.display)
