"""PlatformIO pre-script: build with include/config.h if it exists, else include/config.example.h.

A plain __has_include("config.h") is not usable: the Xtensa toolchain ships its own config.h on the
system include path, so the check would always succeed.
"""

import os

Import("env")  # noqa: F821  (provided by PlatformIO/SCons)

if os.path.isfile(os.path.join(env.subst("$PROJECT_DIR"), "include", "config.h")):  # noqa: F821
    env.Append(CPPDEFINES=["DWELL_HAVE_CONFIG_H"])  # noqa: F821
    print("dwell: using include/config.h")
else:
    print("dwell: include/config.h not found - using include/config.example.h")
