import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.automation_notifications import (
    NotificationQueue, MqttNotificationBridge, TelegramAdapter, NotificationDeliveryWorker, discovery, MAX_PENDING,
)


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'notifications.sqlite3'
        self.queue = NotificationQueue(self.path)
        self.now = 1792674000

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, ident='fridge-off', text='Fridge switched off', at=None):
        return json.dumps(dict(schema=1, id=ident,
            created_at=datetime.fromtimestamp(self.now if at is None else at, timezone.utc).isoformat(),
            message=text))

    def test_restart_duplicate_and_successful_delivery_are_persistent(self):
        self.assertEqual('accepted', self.queue.accept(self.payload(), now=self.now))
        restarted = NotificationQueue(self.path)
        self.assertEqual(self.queue.instance, restarted.instance)
        self.assertEqual('duplicate', restarted.accept(self.payload(), now=self.now))
        adapter = Mock()
        self.assertTrue(restarted.deliver_one(adapter, now=self.now))
        adapter.send.assert_called_once_with('Fridge switched off')
        self.assertFalse(NotificationQueue(self.path).deliver_one(adapter, now=self.now+30))
        self.assertEqual('duplicate', self.queue.accept(self.payload(), now=self.now+30))

    def test_quiet_hours_then_retry_never_execute_device_action(self):
        self.queue.accept(self.payload(), now=self.now)
        adapter = Mock()
        self.assertFalse(self.queue.deliver_one(adapter, quiet=True, now=self.now))
        adapter.send.assert_not_called()
        adapter.send.side_effect = OSError('temporary')
        self.assertFalse(self.queue.deliver_one(adapter, now=self.now))
        self.assertFalse(self.queue.deliver_one(adapter, now=self.now+29))
        adapter.send.side_effect = None
        self.assertTrue(self.queue.deliver_one(adapter, now=self.now+31))
        self.assertEqual(2, adapter.send.call_count)

    def test_retained_expired_malformed_oversized_and_arbitrary_destinations_rejected(self):
        self.assertEqual('invalid', self.queue.accept(self.payload(), retained=True, now=self.now))
        self.assertEqual('expired', self.queue.accept(self.payload(at=self.now-86401), now=self.now))
        self.assertEqual('expired', self.queue.accept(self.payload(at=self.now+61), now=self.now))
        for value in ('[]', '{}', 'not json', self.payload(text=' '), self.payload(text='x'*2001)):
            self.assertEqual('invalid', self.queue.accept(value, now=self.now))
        value = json.loads(self.payload());value['chat_id']='unconfigured'
        self.assertEqual('invalid', self.queue.accept(json.dumps(value), now=self.now))
        self.assertEqual(0, self.queue.status()['pending'])

    def test_bound_and_expiry_do_not_drop_unexpired_pending_requests(self):
        for n in range(MAX_PENDING):
            self.assertEqual('accepted', self.queue.accept(self.payload(str(n)), now=self.now))
        self.assertEqual('full', self.queue.accept(self.payload('extra'), now=self.now))
        adapter = Mock()
        self.assertFalse(self.queue.deliver_one(adapter, now=self.now+86401))
        adapter.send.assert_not_called()
        self.assertEqual(MAX_PENDING, self.queue.status()['expired'])

    def test_plain_text_is_escaped_and_destination_is_local(self):
        telegram = Mock()
        TelegramAdapter(telegram, 'configured-family').send('<b>Boiler & fridge</b>')
        telegram.send_message.assert_called_once_with('configured-family', '&lt;b&gt;Boiler &amp; fridge&lt;/b&gt;')

    def test_delivery_worker_is_independent_of_household_polling(self):
        now=datetime.now(timezone.utc).timestamp()
        self.queue.accept(self.payload(at=now),now=now)
        delivered=threading.Event();adapter=Mock();adapter.send.side_effect=lambda _:delivered.set()
        worker=NotificationDeliveryWorker(self.queue,Mock(),adapter,quiet=lambda:False)
        try:
            worker.start()
            self.assertTrue(delivered.wait(2))
        finally:
            worker.stop()
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(1,self.queue.status()['sent'])

    def test_availability_waits_for_request_subscription(self):
        client=Mock();client.subscribe.side_effect=[(0,10),(0,11)]
        config=SimpleNamespace(notification_mqtt_user='',notification_mqtt_password='')
        bridge=MqttNotificationBridge(config,self.queue,mqtt_factory=lambda:client)
        bridge.on_connect(client,None,None,0)
        bridge.on_subscribe(client,None,11,[SimpleNamespace(is_failure=False)])
        self.assertFalse(bridge.online)
        bridge.on_subscribe(client,None,10,[SimpleNamespace(is_failure=False)])
        self.assertTrue(bridge.online)
        bridge.on_disconnect(client,None,None,1)
        self.assertFalse(bridge.online)

    def test_fridge_off_and_on_each_generate_one_message(self):
        client=Mock()
        bridge=MqttNotificationBridge(SimpleNamespace(notification_mqtt_user='',notification_mqtt_password=''),
            self.queue,mqtt_factory=lambda:client)
        for ident in ('fridge-off','fridge-on'):
            message=SimpleNamespace(topic=bridge.root+'/request',
                payload=self.payload(ident, ident, at=datetime.now(timezone.utc).timestamp()).encode(),retain=False)
            bridge.on_message(client,None,message)
            bridge.on_message(client,None,message)
        telegram=Mock();adapter=TelegramAdapter(telegram,'configured-family')
        self.assertTrue(self.queue.deliver_one(adapter))
        self.assertTrue(self.queue.deliver_one(adapter))
        self.assertFalse(self.queue.deliver_one(adapter))
        self.assertEqual(2,telegram.send_message.call_count)


if __name__ == '__main__':
    unittest.main()
