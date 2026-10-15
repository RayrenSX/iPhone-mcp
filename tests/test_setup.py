import json
import tempfile
import threading
import time
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch, Mock

from iphonemirror_mcp.setup import ASSET, SetupFailure, SetupGate, SetupJobs, checksum, driver_id, driver_events


class SetupTests(unittest.TestCase):
    def test_driver_launch_restores_windir_in_filtered_client_environment(self):
        import win32api
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'mcp-runtime.json').write_text('{"driverSetupVersion":1}')
            with patch.dict('os.environ', {'LOCALAPPDATA': directory}, clear=True), patch(
                'iphonemirror_mcp.setup.subprocess.Popen', return_value=Mock(poll=Mock(return_value=0))) as launch:
                self.assertEqual(list(driver_events(folder / 'iPhoneMirror.exe', 'diagnose')), [])
                self.assertEqual(launch.call_args.kwargs['env']['windir'], win32api.GetWindowsDirectory())

    def finish(self, jobs, status):
        deadline = time.monotonic() + 3
        while status['state'] == 'running' and time.monotonic() < deadline:
            time.sleep(.01)
            status = jobs.status(status['jobId'])
        self.assertNotEqual(status['state'], 'running')
        return status

    def run_events(self, events, **kwargs):
        jobs = SetupJobs(lambda: Path('iPhoneMirror.exe'))
        with patch('iphonemirror_mcp.setup.SetupGate', return_value=nullcontext()), patch(
            'iphonemirror_mcp.setup.driver_events', side_effect=events) as native:
            status = self.finish(jobs, jobs.begin(**kwargs))
        return status, native.call_count

    def inventory(self, count=1, healthy=False):
        return iter([{'Stage': 'Result', 'Success': True, 'Devices': [
            {'Serial': f'private-{i}', 'Healthy': healthy, 'FilterInstalled': healthy}
            for i in range(count)], 'Environment': {
                'AppleReady': healthy, 'UsbFilesMatch': healthy, 'UsbRunning': healthy}}])

    def test_manifest_requires_exact_one_entry(self):
        entry = 'a' * 64 + '  ' + ASSET + '\n'
        self.assertEqual(checksum(entry), 'a' * 64)
        for invalid in ('', entry + entry, entry.replace(ASSET, 'other.zip')):
            with self.assertRaises(SetupFailure):
                checksum(invalid)

    def test_healthy_driver_is_never_prepared(self):
        result, calls = self.run_events([self.inventory(healthy=True)])
        self.assertEqual(calls, 1)
        self.assertEqual(result['state'], 'completed')
        self.assertFalse(result['phoneReady'])
        self.assertNotIn('private-', json.dumps(result))

    def test_missing_and_multiple_devices_require_user_action(self):
        for count, action in ((0, 'connect_usb'), (2, 'select_device')):
            result, calls = self.run_events([self.inventory(count)])
            self.assertEqual(result['actionRequired'], action)
            self.assertEqual(calls, 1)

    def test_selected_device_replug_is_not_completed(self):
        result, calls = self.run_events([self.inventory(2), iter([{'Stage': 'Replug'}])],
                                       device_id=driver_id('private-1'))
        self.assertEqual(calls, 2)
        self.assertEqual(result['state'], 'action_required')
        self.assertEqual(result['actionRequired'], 'replug_usb')

    def test_uncertain_result_never_retries(self):
        result, calls = self.run_events([self.inventory(), iter([])])
        self.assertEqual(calls, 2)
        self.assertEqual(result['errorCode'], 'DRIVER_OUTCOME_UNKNOWN')
        self.assertFalse(result['retryAllowed'])

    def test_uac_cancel_is_actionable_and_redacts_detail(self):
        result, calls = self.run_events([self.inventory(), iter([
            {'Stage': 'AppleFailed', 'Detail': 'private-secret user cancelled'}])])
        self.assertEqual(result['actionRequired'], 'confirm_uac')
        self.assertNotIn('private-secret', json.dumps(result))

    def test_concurrent_job_is_coalesced(self):
        waiting = threading.Event()
        jobs = SetupJobs(lambda: (waiting.wait(2), Path('app'))[1])
        with patch('iphonemirror_mcp.setup.SetupGate', return_value=nullcontext()):
            first = jobs.begin(install_drivers=False)
            second = jobs.begin(install_drivers=False)
            self.assertEqual(first['jobId'], second['jobId'])
            self.assertTrue(second['reused'])
            waiting.set()
            self.finish(jobs, first)

    def test_os_gate_excludes_another_client_and_releases(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', LOCALAPPDATA=directory):
            with SetupGate():
                with self.assertRaisesRegex(SetupFailure, 'SETUP_BUSY'):
                    with SetupGate():
                        pass
            with SetupGate():
                pass

    def test_revision_wait_wakes_on_completion_and_terminal_reads_return_immediately(self):
        release = threading.Event()
        results = []
        jobs = SetupJobs(lambda: (release.wait(3), Path('app'))[1])
        with patch('iphonemirror_mcp.setup.SetupGate', return_value=nullcontext()):
            first = jobs.begin(install_drivers=False)
            reader = threading.Thread(target=lambda: results.append(jobs.status(first['jobId'], first['revision'], 20)))
            reader.start()
            try:
                unchanged = jobs.status(first['jobId'], first['revision'], .02)
                self.assertEqual(unchanged, first)
                release.set()
                reader.join(2)
                self.assertFalse(reader.is_alive())
                self.assertEqual(results[0]['state'], 'completed')
                self.assertGreater(results[0]['revision'], first['revision'])
                started = time.monotonic()
                terminal = jobs.status(first['jobId'], results[0]['revision'], 20)
                self.assertEqual(terminal, results[0])
                self.assertLess(time.monotonic() - started, 1)
                terminal['state'] = 'changed by caller'
                self.assertEqual(jobs.status(first['jobId'])['state'], 'completed')
            finally:
                release.set()
                reader.join(2)

    def test_revision_wait_returns_human_action_and_unknown_jobs_fail(self):
        release = threading.Event()
        results = []
        jobs = SetupJobs(lambda: (release.wait(3), Path('app'))[1])
        with patch('iphonemirror_mcp.setup.SetupGate', return_value=nullcontext()), patch(
            'iphonemirror_mcp.setup.driver_events', return_value=self.inventory(0)):
            first = jobs.begin()
            # Wait beyond the next revision to prove human/terminal states break the wait independently.
            reader = threading.Thread(target=lambda: results.append(jobs.status(first['jobId'], 1000, 20)))
            reader.start()
            try:
                release.set()
                reader.join(2)
                self.assertFalse(reader.is_alive())
                self.assertEqual(results[0]['actionRequired'], 'connect_usb')
                self.assertEqual(results[0]['state'], 'action_required')
            finally:
                release.set()
                reader.join(2)
        with self.assertRaisesRegex(RuntimeError, 'SETUP_JOB_NOT_FOUND'):
            jobs.status('unknown', 0, 20)
