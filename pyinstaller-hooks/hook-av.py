"""PyInstaller hook for PyAV: bundle the FFmpeg runtime DLLs.

PyAV's wheels ship the FFmpeg shared libraries in a *sibling* directory
called ``av.libs/`` (delvewheel layout), e.g.::

    site-packages/
        av/            <- the Python package (--collect-all av gets this)
        av.libs/       <- avcodec-63-....dll, avformat-63-....dll, ...

``--collect-all av`` only collects the ``av`` package itself, so a frozen
app ends up without any codecs and ``import av`` fails with a DLL load
error. At runtime ``av/__init__.py`` calls
``os.add_dll_directory(<pardir>/av.libs)``, so we mirror that layout in
the bundle: binaries below land in ``<bundle>/av.libs/``.

Without this hook the built EXE cannot play anything (every play()
call just emits "error").
"""

import os

binaries = []

try:
    import av  # noqa: F401  (only used to locate the package)

    _pkg_dir = os.path.dirname(av.__file__)
    _libs_dir = os.path.join(os.path.dirname(_pkg_dir), "av.libs")
    if os.path.isdir(_libs_dir):
        for _name in sorted(os.listdir(_libs_dir)):
            if _name.lower().endswith((".dll", ".so", ".dylib")):
                # (source_path, destination_dir_inside_bundle)
                binaries.append((os.path.join(_libs_dir, _name), "av.libs"))
except Exception:
    # Hook-time failure must never break the build; worst case the
    # frozen app reports the missing engine via Player.last_error.
    pass
