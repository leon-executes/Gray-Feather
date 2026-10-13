"""Download assembly and trim boundaries. Synthetic files only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools.package_delivery import github_parts
from tools.trim_portable import trim

@unittest.skipIf(getattr(sys, 'frozen', False), 'Source-only packaging tools')
class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def parts(self):
        source = self.root/'complete.zip'
        source.write_bytes(bytes(range(256))*777 + b'final byte')
        result = github_parts(source, self.root, part_size=65536)
        return source, self.root/'GitHub-Release', result

    def join(self, folder):
        powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        return subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(folder/'Join-GrayFeather.ps1')], capture_output=True, timeout=30)

    def test_parts_rejoin_byte_exactly_and_repeated_run_preserves_result(self):
        source, folder, manifest = self.parts()
        self.assertEqual(sum(p['bytes'] for p in manifest['parts']), source.stat().st_size)
        self.assertEqual(self.join(folder).returncode, 0)
        self.assertEqual((folder/source.name).read_bytes(), source.read_bytes())
        self.assertEqual(self.join(folder).returncode, 0)

    def test_corrupt_part_fails_without_creating_output(self):
        source, folder, manifest = self.parts()
        part = folder/manifest['parts'][0]['name']
        raw = bytearray(part.read_bytes());raw[3] ^= 1;part.write_bytes(raw)
        self.assertNotEqual(self.join(folder).returncode, 0)
        self.assertFalse((folder/source.name).exists())
        self.assertEqual(list(folder.glob('*.tmp')), [])

    def test_missing_part_fails_without_creating_output(self):
        source, folder, manifest = self.parts()
        (folder/manifest['parts'][-1]['name']).unlink()
        self.assertNotEqual(self.join(folder).returncode, 0)
        self.assertFalse((folder/source.name).exists())

    def test_existing_different_zip_is_never_overwritten(self):
        source, folder, manifest = self.parts()
        target = folder/source.name;target.write_bytes(b'Keep this file')
        self.assertNotEqual(self.join(folder).returncode, 0)
        self.assertEqual(target.read_bytes(), b'Keep this file')

    def test_trim_keeps_private_copy_and_unrelated_libraries(self):
        internal=self.root/'_internal';private=internal/'resources/offline-voice/piper'
        private.mkdir(parents=True)
        (private/'espeak-ng.dll').write_bytes(b'identical library')
        (internal/'espeak-ng.dll').write_bytes(b'identical library')
        (internal/'python312.dll').write_bytes(b'keep shared runtime')
        result=trim(self.root)
        self.assertEqual(len(result['removed']),1)
        self.assertTrue((private/'espeak-ng.dll').exists())
        self.assertTrue((internal/'python312.dll').exists())

    def test_trim_refuses_nonidentical_library(self):
        internal=self.root/'_internal';private=internal/'resources/offline-voice/piper'
        private.mkdir(parents=True)
        (private/'espeak-ng.dll').write_bytes(b'new library')
        (internal/'espeak-ng.dll').write_bytes(b'old library')
        with self.assertRaises(ValueError):trim(self.root)
        self.assertTrue((internal/'espeak-ng.dll').exists())
