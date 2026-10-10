"""Integration regression probes; synthetic audio, no device/provider activity."""
import ctypes
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import speech

TEMP_ROOT = None  # self-test runner selects a writable disposable data directory


def pcm(frames=32):
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * frames)
    return audio.getvalue()


class NativeFunction:
    def __init__(self, function):
        self.function = function
    def __call__(self, *args):
        return self.function(*args)


class FakeWinMM:
    def __init__(self):
        self.headers = []
        self.reset_count = 0
        self.unprepared = 0
        self.closed = 0
        self.waveInOpen = NativeFunction(self.open)
        self.waveInPrepareHeader = NativeFunction(self.prepare)
        self.waveInAddBuffer = NativeFunction(self.add)
        self.waveInStart = NativeFunction(self.start)
        self.waveInStop = NativeFunction(lambda handle: 0)
        self.waveInReset = NativeFunction(self.reset)
        self.waveInUnprepareHeader = NativeFunction(self.unprepare)
        self.waveInClose = NativeFunction(self.close)
    def open(self, pointer, *args):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p)).contents.value = 123
        return 0
    def prepare(self, handle, pointer, size):
        self.headers.append(ctypes.cast(pointer, ctypes.POINTER(speech.WaveHeader)).contents)
        return 0
    def add(self, handle, pointer, size):
        header = ctypes.cast(pointer, ctypes.POINTER(speech.WaveHeader)).contents
        header.flags = 0
        header.recorded = 0
        return 0
    def start(self, handle):
        for index, byte in ((0, b'A'), (1, b'B')):
            header = self.headers[index]
            ctypes.memmove(header.data, byte * 6400, 6400)
            header.recorded = 6400
            header.flags = 1
        return 0
    def reset(self, handle):
        self.reset_count += 1
        if self.reset_count == 1:
            # Queue has rotated to [2,3,0,1]. Header2 contains the final partial block.
            header = self.headers[2]
            ctypes.memmove(header.data, b'C' * 2000, 2000)
            header.recorded = 2000
        for header in self.headers:
            header.flags |= 1
        return 0
    def unprepare(self, handle, pointer, size):
        self.unprepared += 1
        return 0
    def close(self, handle):
        self.closed += 1
        return 0


class StopOnWait(threading.Event):
    def wait(self, timeout=None):
        self.set()
        return True


class RecordingOrderTests(unittest.TestCase):
    def test_delayed_stop_caps_complete_frame_count_and_reports_limit(self):
        clock = [0.0]
        class DelayedWinMM(FakeWinMM):
            def fill(self):
                for index, header in enumerate(self.headers):
                    ctypes.memmove(header.data, bytes([index + 1]) * 6400, 6400)
                    header.recorded = 6400
                    header.flags = 1
            def start(self, handle):
                clock[0] = .8
                self.fill()
                return 0
            def reset(self, handle):
                self.reset_count += 1
                for header in self.headers:
                    header.flags |= 1
                return 0
        fake = DelayedWinMM()
        class DelayedStop(threading.Event):
            def wait(self, timeout=None):
                clock[0] += .8
                fake.fill()
                return False
        with patch('speech.ctypes.WinDLL', return_value=fake), patch('speech.time.monotonic', side_effect=lambda: clock[0]):
            audio, metadata = speech.record_wav(DelayedStop())
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            self.assertEqual(wav.getnframes(), 800000)
        self.assertEqual(len(speech._pcm16(audio)), 1600000)
        self.assertEqual(metadata['duration_ms'], 50000)
        self.assertTrue(metadata['limit_reached'])
        self.assertFalse(metadata['complete'])
        self.assertEqual(fake.unprepared, 4)
        self.assertEqual(fake.closed, 1)

    def test_rotated_queue_preserves_final_partial_and_order(self):
        fake = FakeWinMM()
        with patch('speech.ctypes.WinDLL', return_value=fake):
            audio, metadata = speech.record_wav(StopOnWait())
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            self.assertEqual(wav.readframes(wav.getnframes()), b'A' * 6400 + b'B' * 6400 + b'C' * 2000)
        self.assertEqual(fake.unprepared, 4)
        self.assertEqual(fake.closed, 1)
        self.assertFalse(metadata['limit_reached'])


class CloudVoiceBoundaryTests(unittest.TestCase):
    def config(self, directory):
        return {'speech_key': 'synthetic-not-real', 'speech_region': 'uksouth',
                'speech_provider': 'azure', '_audio_dir': directory}

    def test_truncated_pcm_never_starts_playback(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            with patch('speech.request', return_value=pcm()[:-2]), patch('speech.winsound.PlaySound') as play:
                with self.assertRaises(Exception):
                    speech.speak_azure('Synthetic test', 'en-US', self.config(directory), threading.Event())
            play.assert_not_called()
            self.assertEqual(list(Path(directory).glob('*.wav')), [])

    def test_empty_pcm_never_counts_as_complete_voice(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            with patch('speech.request', return_value=pcm(0)), patch('speech.winsound.PlaySound') as play:
                with self.assertRaises(speech.SpeechError):
                    speech.speak_azure('Synthetic test', 'en-US', self.config(directory), threading.Event())
            play.assert_not_called()

    def test_player_failure_still_removes_private_audio(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            with patch('speech.request', return_value=pcm()), patch('speech.winsound.PlaySound', side_effect=RuntimeError('synthetic output failure')):
                with self.assertRaises(Exception):
                    speech.speak_azure('Synthetic test', 'en-US', self.config(directory), threading.Event())
            self.assertEqual(list(Path(directory).glob('*.wav')), [])

    def test_cancel_during_http_never_starts_returned_audio(self):
        stop = threading.Event()
        def response(*args, **kwargs):
            stop.set()
            return pcm()
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            with patch('speech.request', side_effect=response), patch('speech.winsound.PlaySound') as play:
                try:
                    speech.speak_azure('Synthetic test', 'en-US', self.config(directory), stop)
                except speech.SpeechError:
                    pass
            self.assertFalse(any(call.args and call.args[0] for call in play.call_args_list))
            self.assertEqual(list(Path(directory).glob('*.wav')), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
