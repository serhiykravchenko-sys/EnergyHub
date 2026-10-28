"""Offline address transactions, including failed and interrupted changes."""
import importlib.util
from pathlib import Path
from copy import deepcopy
import unittest

path = Path(__file__).resolve().parents[1]/'live/config/custom_components/energyhub_network/endpoint.py'
spec = importlib.util.spec_from_file_location('eh_endpoint', path)
endpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(endpoint)


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {'devices': [{'mac_address': 'device-a', 'ip_address': '192.168.10.10',
                                 'lanip_key': 'sentinel', 'name': 'Heat pump'}], 'manual': 'preserve'}
        self.journal = {}
        self.saved = []
        self.writes = []
        self.result = True
        async def save(value):
            self.saved.append(deepcopy(value))
        def update(entry, data):
            self.data = data
            self.writes.append(deepcopy(data))
        async def verify(entry, mac, ip):
            return self.result or ip == '192.168.10.10'
        self.editor = endpoint.Editor(self.journal, save, lambda entry: self.data, update, verify)

    async def test_success_preserves_other_settings_and_persists_before_write(self):
        await self.editor.apply('entry', 'device-a', '192.168.10.11')
        self.assertEqual('192.168.10.11', self.data['devices'][0]['ip_address'])
        self.assertEqual('sentinel', self.data['devices'][0]['lanip_key'])
        self.assertEqual('preserve', self.data['manual'])
        self.assertIn('pending', self.saved[0])
        self.assertNotIn('pending', self.saved[-1])
        self.assertEqual('verified', self.journal['status'])

    async def test_timeout_rolls_back_and_reports_failure(self):
        self.result = False
        with self.assertRaisesRegex(ValueError, 'fresh authenticated'):
            await self.editor.apply('entry', 'device-a', '192.168.10.11')
        self.assertEqual('192.168.10.10', self.data['devices'][0]['ip_address'])
        self.assertEqual('rolled_back', self.journal['status'])

    async def test_interrupted_transaction_recovers(self):
        self.journal['pending'] = dict(entry='entry', mac='device-a', old='192.168.10.10', new='192.168.10.11')
        self.data['devices'][0]['ip_address'] = '192.168.10.11'
        await self.editor.recover()
        self.assertEqual('192.168.10.10', self.data['devices'][0]['ip_address'])
        self.assertNotIn('pending', self.saved[-1])

    async def test_independent_change_is_preserved(self):
        self.journal['pending'] = dict(entry='entry', mac='device-a', old='192.168.10.10', new='192.168.10.11')
        self.data['devices'][0]['ip_address'] = '192.168.10.12'
        await self.editor.recover()
        self.assertEqual('conflict', self.journal['status'])
        self.assertEqual([], self.writes)

    async def test_interruption_before_write_leaves_original_unchanged(self):
        self.journal['pending'] = dict(entry='entry', mac='device-a', old='192.168.10.10', new='192.168.10.11')
        await self.editor.recover()
        self.assertEqual('already_restored', self.journal['status'])
        self.assertEqual([], self.writes)

    async def test_invalid_targets_addresses_and_noop_do_not_write(self):
        for value in ('8.8.8.8', '127.0.0.1', '169.254.1.1', '192.168.10.255', 'bad'):
            with self.assertRaises(ValueError):
                await self.editor.apply('entry', 'device-a', value)
        with self.assertRaises(ValueError):
            await self.editor.apply('entry', 'unrelated', '192.168.10.11')
        self.assertFalse(await self.editor.apply('entry', 'device-a', '192.168.10.10'))
        self.assertEqual([], self.writes)
