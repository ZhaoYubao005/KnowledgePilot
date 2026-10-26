"""Timeout cleanup must terminate the owned verifier's descendants, not only its parent."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ProcessCleanupTests(unittest.TestCase):
    def test_timeout_stops_parent_and_descendant(self):
        path = ROOT / 'scripts/integration/processes.py'
        self.assertTrue(path.is_file(), 'owned-process runner is not implemented')
        spec = importlib.util.spec_from_file_location('step4_processes', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            pid_file = Path(folder) / 'child.json'
            code = ('import subprocess,sys,time,json,os; '
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                    'open(sys.argv[1],"w").write(json.dumps([os.getpid(),p.pid])); time.sleep(60)')
            with self.assertRaises(subprocess.TimeoutExpired):
                module.run_owned([sys.executable, '-B', '-c', code, str(pid_file)],
                                 cwd=folder, env=dict(os.environ), timeout=2)
            self.assertTrue(pid_file.is_file(), 'child did not start before timeout')
            for pid in json.loads(pid_file.read_text()):
                if os.name == 'nt':
                    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                    kernel.OpenProcess.restype = ctypes.c_void_p
                    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                    handle = kernel.OpenProcess(0x00100000, False, pid)
                    if handle:
                        try:
                            self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0, 'owned process still alive')
                        finally:
                            kernel.CloseHandle(handle)
                else:
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            break
                        stat = Path(f'/proc/{pid}/stat')
                        if stat.is_file() and stat.read_text().split(') ', 1)[1].startswith('Z'):
                            break
                        time.sleep(0.05)
                    else:
                        self.fail('owned process still alive')
