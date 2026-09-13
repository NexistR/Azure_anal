"""Extract a local cached CPython 3.12 MSI runtime without installing it.

Windows only. Reads MSI databases with Windows Installer's read-only API and
extracts their embedded CAB files with expand.exe. All writes stay below the
specified destination. No registry changes and no downloads occur.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import shutil
import subprocess
import tempfile


class MsiReader:
    def __init__(self, path):
        self.api = ctypes.WinDLL("msi")
        self.api.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
        self.api.MsiDatabaseOpenViewW.argtypes = [wintypes.UINT, wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT)]
        self.api.MsiViewExecute.argtypes = [wintypes.UINT, wintypes.UINT]
        self.api.MsiViewFetch.argtypes = [wintypes.UINT, ctypes.POINTER(wintypes.UINT)]
        self.api.MsiRecordGetStringW.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.api.MsiRecordReadStream.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        self.handle = wintypes.UINT()
        self.check(self.api.MsiOpenDatabaseW(str(path), None, ctypes.byref(self.handle)))

    @staticmethod
    def check(code):
        if code:
            raise OSError(code, "Windows Installer read failed")

    def records(self, sql):
        view = wintypes.UINT()
        self.check(self.api.MsiDatabaseOpenViewW(self.handle, sql, ctypes.byref(view)))
        try:
            self.check(self.api.MsiViewExecute(view, 0))
            while True:
                record = wintypes.UINT()
                code = self.api.MsiViewFetch(view, ctypes.byref(record))
                if code == 259:
                    break
                self.check(code)
                try:
                    yield record
                finally:
                    self.api.MsiCloseHandle(record)
        finally:
            self.api.MsiCloseHandle(view)

    def string(self, record, index):
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        self.check(self.api.MsiRecordGetStringW(record, index, buf, ctypes.byref(size)))
        return buf.value

    def table(self, name, columns):
        return [[self.string(record, i) for i in range(1, columns + 1)]
                for record in self.records("SELECT * FROM " + name)]

    def extract_stream(self, name, destination):
        for record in self.records("SELECT Data FROM _Streams WHERE Name = '" + name + "'"):
            with destination.open("wb") as output:
                while True:
                    size = wintypes.DWORD(65536)
                    buf = ctypes.create_string_buffer(size.value)
                    self.check(self.api.MsiRecordReadStream(record, 1, buf, ctypes.byref(size)))
                    if not size.value:
                        break
                    output.write(buf.raw[:size.value])

    def close(self):
        self.api.MsiCloseHandle(self.handle)


def extract_package(msi_path, destination):
    reader = MsiReader(msi_path)
    try:
        directories = {row[0]: (row[1], row[2]) for row in reader.table("Directory", 3)}
        components = {row[0]: row[2] for row in reader.table("Component", 6)}

        def directory(name):
            if name in ("TARGETDIR", "InstallDirectory", ""):
                return destination
            parent, folder = directories[name]
            folder = folder.split(":")[0].split("|")[-1]
            return directory(parent) / ("" if folder == "." else folder)

        with tempfile.TemporaryDirectory(prefix="extract_", dir=destination.parent) as tmp:
            temporary = Path(tmp)
            for media in reader.table("Media", 6):
                cabinet = media[3]
                if not cabinet.startswith("#"):
                    raise RuntimeError("Expected an embedded cabinet")
                cab = temporary / cabinet[1:]
                reader.extract_stream(cabinet[1:], cab)
                subprocess.run(["expand.exe", str(cab), "-F:*", str(temporary)],
                               check=True, stdout=subprocess.DEVNULL)
            count = 0
            for row in reader.table("File", 8):
                target = directory(components[row[1]]) / row[2].split("|")[-1]
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError("MSI destination escapes runtime root")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(temporary / row[0], target)
                count += 1
        print(f"Extracted {msi_path.name}: {count} files")
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for package in ("core", "exe", "lib"):
        matches = sorted(args.cache.glob("*v3.12.9150.0/" + package + ".msi"))
        if len(matches) != 1:
            raise RuntimeError(f"Expected one cached Python 3.12.9 {package}.msi; got {matches}")
        extract_package(matches[0], destination)
    subprocess.run([str(destination / "python.exe"), "--version"], check=True)


if __name__ == "__main__":
    main()
