"""Messaging-only native HA notify bridge; never executes appliance actions."""
from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger(__name__)
MAX_PENDING = 256
MAX_TEXT = 2000
MAX_AGE = 86400


class NotificationQueue:
    """Independent transactional outbox; acceptance survives app restarts."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', ('instance', uuid.uuid4().hex))
            self.instance = db.execute('SELECT value FROM meta WHERE key=?', ('instance',)).fetchone()[0]
            db.execute('''CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, created REAL NOT NULL, message TEXT NOT NULL,
                status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_at REAL NOT NULL DEFAULT 0)''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def accept(self, payload, *, retained=False, now=None):
        now = time.time() if now is None else now
        if retained or not isinstance(payload, str) or len(payload.encode('utf-8')) > 16000:
            return 'invalid'
        try:
            item = json.loads(payload)
            if (not isinstance(item, dict) or set(item) != {'schema', 'id', 'created_at', 'message'}
                    or type(item['schema']) is not int or item['schema'] != 1
                    or not isinstance(item['id'], str)
                    or not re.fullmatch(r'[A-Za-z0-9_.:+-]{1,100}', item['id'])
                    or not isinstance(item['message'], str)
                    or not 1 <= len(item['message'].strip()) <= MAX_TEXT):
                return 'invalid'
            at = datetime.fromisoformat(item['created_at'])
            if at.tzinfo is None or not -60 <= now-at.timestamp() <= MAX_AGE:
                return 'expired'
        except (ValueError, TypeError, KeyError, RecursionError):
            return 'invalid'
        with self.lock, self.connection() as db:
            # Keep IDs for seven days. Pending messages have their own one-day TTL.
            db.execute("DELETE FROM messages WHERE created < ? AND status != 'pending'", (now-7*86400,))
            db.execute("UPDATE messages SET status='expired',message='' WHERE status='pending' AND created < ?", (now-MAX_AGE,))
            if db.execute('SELECT 1 FROM messages WHERE id=?', (item['id'],)).fetchone():
                return 'duplicate'
            count = db.execute("SELECT count(*) FROM messages WHERE status='pending'").fetchone()[0]
            if count >= MAX_PENDING:
                return 'full'
            # Also bound completed history during a sustained producer flood.
            db.execute("DELETE FROM messages WHERE id IN (SELECT id FROM messages WHERE status!='pending' ORDER BY created DESC LIMIT -1 OFFSET 2048)")
            db.execute('INSERT INTO messages (id,created,message,status) VALUES (?,?,?,?)',
                       (item['id'], at.timestamp(), item['message'], 'pending'))
        return 'accepted'

    def deliver_one(self, adapter, *, quiet=False, now=None, timezone_name='UTC'):
        """Only the main delivery thread calls this; all writes are committed."""
        now = time.time() if now is None else now
        with self.lock, self.connection() as db:
            db.execute("UPDATE messages SET status='expired',message='' WHERE status='pending' AND created < ?", (now-MAX_AGE,))
            if quiet:
                return False
            row = db.execute("SELECT id,message,attempts,created FROM messages WHERE status='pending' AND next_at<=? ORDER BY created LIMIT 1", (now,)).fetchone()
            if not row:
                return False
            ident, message, attempts, created = row
            # Persist a retry delay before I/O. A crash after Telegram accepts
            # but before local acknowledgement can still duplicate a send.
            db.execute('UPDATE messages SET attempts=?, next_at=? WHERE id=?',
                       (attempts+1, now+min(3600, 30*2**min(attempts, 7)), ident))
        try:
            if now-created > 300:
                at = datetime.fromtimestamp(created, ZoneInfo(timezone_name))
                message = f'[{at:%d.%m %H:%M %Z}]\n'+message
            adapter.send(message)
        except Exception:
            LOGGER.warning('Automation notification delivery failed; queued for retry')
            return False
        with self.lock, self.connection() as db:
            db.execute("UPDATE messages SET status='sent', message='' WHERE id=?", (ident,))
        return True

    def status(self):
        with self.lock, self.connection() as db:
            counts = dict(db.execute('SELECT status,count(*) FROM messages GROUP BY status'))
            retrying = db.execute("SELECT count(*) FROM messages WHERE status='pending' AND attempts>0").fetchone()[0]
            last = db.execute("SELECT id FROM messages WHERE status='sent' ORDER BY created DESC LIMIT 1").fetchone()
        return dict(pending=counts.get('pending', 0), sent=counts.get('sent', 0),
                    expired=counts.get('expired', 0), retrying=retrying,
                    last_sent_id=last[0] if last else None)


class TelegramAdapter:
    """Destination is configured locally, never supplied by incoming text."""

    def __init__(self, telegram, destination):
        self.telegram, self.destination = telegram, destination

    def send(self, message):
        self.telegram.send_message(self.destination, html.escape(message))


class NotificationDeliveryWorker:
    """Delivery cannot wait behind calendar/weather/household polling."""

    def __init__(self, queue, bridge, adapter, quiet, timezone_name='UTC'):
        self.queue, self.bridge, self.adapter, self.quiet = queue, bridge, adapter, quiet
        self.timezone_name = timezone_name
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self.run, name='automation-notifications', daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        failed = False
        while not self.stopping.is_set():
            try:
                self.queue.deliver_one(self.adapter, quiet=self.quiet(), timezone_name=self.timezone_name)
                self.bridge.publish_status()
                if failed:
                    LOGGER.info('Automation notification worker/status checks recovered; queued delivery status is separate')
                failed = False
            except Exception:
                if not failed:
                    LOGGER.warning('Automation notification delivery/status unavailable; will retry')
                failed = True
            self.stopping.wait(5)

    def stop(self):
        self.stopping.set()
        self.thread.join(timeout=2)


def discovery(instance):
    root = f'energyhub/notifications/{instance}'
    device = dict(identifiers=[f'energyhub_messaging_{instance}'], name='EnergyHub messaging', manufacturer='EnergyHub')
    # MQTT's command template receives the message as `value`, not `message`.
    template = ('{% set at = now().isoformat() %}'
                '{{ {"schema": 1, "id": at, "created_at": at, "message": value} | to_json }}')
    common = dict(device=device, availability_topic=root+'/availability')
    notify = dict(common, name='Family Telegram', unique_id=f'energyhub_{instance}_family',
                  default_entity_id='notify.energyhub_family_telegram', command_topic=root+'/request',
                  command_template=template, qos=1, retain=False, icon='mdi:message-text')
    sensor = dict(common, name='Notification delivery', unique_id=f'energyhub_{instance}_delivery',
                  default_entity_id='sensor.energyhub_notification_delivery', state_topic=root+'/status',
                  value_template='{{ value_json.state }}', json_attributes_topic=root+'/status',
                  entity_category='diagnostic', expire_after=90)
    return root, {f'homeassistant/notify/energyhub_{instance}/family/config': notify,
                  f'homeassistant/sensor/energyhub_{instance}/delivery/config': sensor}


class MqttNotificationBridge:
    """Opt-in MQTT transport, with a broker last-will and persistent inbox."""

    def __init__(self, config, queue, *, mqtt_factory=None):
        self.config, self.queue = config, queue
        self.root, self.discovery = discovery(queue.instance)
        self.online = False
        self.rejected = 0
        self.last_status = 0
        self.last_result = 'starting'
        self.request_mid = None
        if mqtt_factory is None:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                      client_id=f'eh-notify-{queue.instance}', clean_session=True)
        else:
            self.client = mqtt_factory()
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.will_set(self.root+'/availability', 'offline', qos=1, retain=True)
        if config.notification_mqtt_user:
            self.client.username_pw_set(config.notification_mqtt_user, config.notification_mqtt_password)
        self.client.reconnect_delay_set(min_delay=2, max_delay=60)

    def start(self):
        self.client.connect_async(self.config.notification_mqtt_host,
                                  self.config.notification_mqtt_port, keepalive=30)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            self.online = False
            LOGGER.warning('Automation notification MQTT connection rejected')
            return
        client.publish(self.root+'/availability', 'offline', qos=1, retain=True)
        for topic, payload in self.discovery.items():
            client.publish(topic, json.dumps(payload), qos=1, retain=True)
        _, self.request_mid = client.subscribe(self.root+'/request', qos=1)
        client.subscribe('homeassistant/status', qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        if mid != self.request_mid or not reason_codes or any(getattr(r, 'is_failure', False) for r in reason_codes):
            return
        self.online = True
        client.publish(self.root+'/availability', 'online', qos=1, retain=True)

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.online = False

    def on_message(self, client, userdata, message):
        if message.topic == 'homeassistant/status':
            if message.payload == b'online':
                for topic, payload in self.discovery.items():
                    client.publish(topic, json.dumps(payload), qos=1, retain=True)
            return
        if message.topic != self.root+'/request':
            return
        try:
            result = self.queue.accept(message.payload.decode('utf-8'), retained=bool(message.retain))
            self.last_result = result
            if result not in {'accepted', 'duplicate'}:
                self.rejected += 1
                LOGGER.warning('Automation notification request rejected: %s', result)
        except (UnicodeError, OSError, sqlite3.Error):
            self.rejected += 1
            self.last_result = 'storage_or_encoding_failure'
            LOGGER.warning('Automation notification acceptance failed; no delivery acknowledgement')

    def publish_status(self, now=None):
        now = time.time() if now is None else now
        if not self.online or now-self.last_status < 30:
            return
        status = self.queue.status()
        status.update(state='retrying' if status['retrying'] else 'queued' if status['pending'] else 'ready', rejected=self.rejected,
                      last_request_result=self.last_result, checked_at=datetime.fromtimestamp(now, timezone.utc).isoformat())
        self.client.publish(self.root+'/status', json.dumps(status), qos=1, retain=True)
        self.last_status = now

    def stop(self):
        self.online = False
        info = self.client.publish(self.root+'/availability', 'offline', qos=1, retain=True)
        try:
            info.wait_for_publish(timeout=2)
        except (RuntimeError, ValueError):
            pass
        self.client.disconnect()
        self.client.loop_stop()
