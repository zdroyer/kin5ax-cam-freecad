# The kin5ax shared library

The addon is a binding: the kinematics, the collision checks and the voxel cutting are all C++, in
[kin5ax](https://github.com/zdroyer/kin5ax), and this folder carries the built library so that the
addon works as installed. The Addon Manager copies files; it cannot compile anything.

| file | built for | built with |
|---|---|---|
| `kin5axc.dll` | Windows x86-64 | MSVC v143, Release |
| `libkin5axc.so` | Linux x86-64 | GCC 15, Release |

Both are version 0.1.0, which is the version this addon is written against. `kin5axcam.kin5ax`
refuses a library whose major and minor differ, so the pair is released together. macOS is not built
yet; on macOS, and on any Linux where the shipped object will not load, build the library and point
the addon at it.

## Where the addon looks

In this order, and it stops at the first file that exists:

1. the path in the environment variable `KIN5AXC_LIBRARY`
2. this folder
3. the build trees of a checkout of the library repository, for development
4. wherever the system loader finds a library of that name

So a developer who builds the library sets `KIN5AXC_LIBRARY` and the shipped file is ignored.

## Building it yourself

```
git clone https://github.com/zdroyer/kin5ax
cd kin5ax
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --target kin5axc
```

The result is `build/kin5axc/Release/kin5axc.dll` on Windows and `build/kin5axc/libkin5axc.so.0.1.0`
on Linux. Copy it here under the plain name, or point `KIN5AXC_LIBRARY` at it.

The Linux object is linked against the C++ runtime of the machine that built it. If FreeCAD reports
that it cannot be loaded, that is almost always a `GLIBCXX` or `GLIBC` too old on the running system,
and building it there is the cure.
