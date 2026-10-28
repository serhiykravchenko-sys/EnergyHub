import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]/'live/config/custom_components/energyhub_network'
package = types.ModuleType('test_network_adapter')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location('test_network_adapter.health', ROOT/'health.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class HealthTests(unittest.IsolatedAsyncioTestCase):
    def test_prefill_and_applied_change_preserve_pending_edit(self):
        self.assertEqual('192.168.10.10', health.helper_update('192.168.10.10', 'unknown', None))
        self.assertEqual('192.168.10.11', health.helper_update('192.168.10.11', '192.168.10.10', '192.168.10.10'))
        self.assertIsNone(health.helper_update('192.168.10.11', '192.168.10.12', '192.168.10.10'))
        self.assertIsNone(health.helper_update(None, 'unknown', None))

    async def test_bounded_single_address_probe_and_exit_classification(self):
        for code, expected in [(0, 'reachable'), (1, 'unreachable'), (2, 'unknown')]:
            process = Mock(returncode=code)
            process.wait = AsyncMock(return_value=code)
            with patch.object(health.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process)) as create:
                self.assertEqual(expected, await health.probe('192.168.10.10'))
                self.assertEqual(('ping', '-c', '1', '-W', '2', '192.168.10.10'), create.call_args.args)

    async def test_unsupported_command_or_invalid_address_is_unknown(self):
        with patch.object(health.asyncio, 'create_subprocess_exec', AsyncMock(side_effect=FileNotFoundError)) as create:
            self.assertEqual('unknown', await health.probe('192.168.10.10'))
            create.reset_mock()
            self.assertEqual('unknown', await health.probe('8.8.8.8'))
            create.assert_not_called()

    async def test_timeout_terminates_probe(self):
        process = Mock(returncode=None)
        process.wait = AsyncMock(return_value=0)
        with patch.object(health.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process)):
            with patch.object(health.asyncio, 'wait_for', AsyncMock(side_effect=TimeoutError)) as wait:
                self.assertEqual('unknown', await health.probe('192.168.10.10'))
                wait.call_args.args[0].close()
        process.kill.assert_called_once()


if __name__ == '__main__': unittest.main()
