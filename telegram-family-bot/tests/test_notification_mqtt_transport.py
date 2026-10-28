"""Real Paho client against a bounded localhost MQTT protocol fixture."""
import json
import socket
import socketserver
import struct
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.automation_notifications import NotificationQueue, MqttNotificationBridge, TelegramAdapter


def packet(header, data):
    length=len(data); encoded=bytearray()
    while True:
        digit=length%128;length//=128
        encoded.append(digit | (128 if length else 0))
        if not length:break
    return bytes([header])+bytes(encoded)+data


def text(value):
    raw=value.encode();return struct.pack('!H',len(raw))+raw


def exact(sock, size):
    raw=b''
    while len(raw)<size:
        part=sock.recv(size-len(raw))
        if not part:raise EOFError
        raw+=part
    return raw


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        try:
            while True:
                header=exact(self.request,1)[0];length=0;factor=1
                while True:
                    digit=exact(self.request,1)[0];length+=(digit&127)*factor;factor*=128
                    if not digit&128:break
                    if factor>128**4:raise ValueError('oversized MQTT frame')
                if length>65536:raise ValueError('oversized fixture packet')
                data=exact(self.request,length)
                kind=header>>4
                if kind==1:
                    self.request.sendall(b'\x20\x02\x00\x00')
                elif kind==8:
                    mid=data[:2];size=struct.unpack('!H',data[2:4])[0]
                    topic=data[4:4+size].decode()
                    self.request.sendall(packet(0x90,mid+b'\x01'))
                    if topic.endswith('/request'):
                        stamp=datetime.now(timezone.utc).isoformat()
                        body=json.dumps(dict(schema=1,id='fridge-confirmed-off',created_at=stamp,
                                             message='Fridge switched off')).encode()
                        # Simulate broker QoS duplicate delivery with same event ID.
                        for ident in (50,51):
                            self.request.sendall(packet(0x32,text(topic)+struct.pack('!H',ident)+body))
                elif kind==3:
                    size=struct.unpack('!H',data[:2])[0];topic=data[2:2+size].decode();pos=2+size
                    if (header>>1)&3:
                        self.request.sendall(packet(0x40,data[pos:pos+2]));pos+=2
                    self.server.published.append((topic,data[pos:],bool(header&1)))
                elif kind==12:
                    self.request.sendall(b'\xd0\x00')
                elif kind==14:
                    return
        except (EOFError,OSError,ValueError):
            return


class TransportTests(unittest.TestCase):
    def test_real_mqtt_discovery_subscription_duplicate_and_outbox(self):
        import paho.mqtt.client  # Dependency is installed by the app image.
        with tempfile.TemporaryDirectory() as tmp:
            server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler)
            server.daemon_threads=True;server.published=[]
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            queue=NotificationQueue(Path(tmp)/'queue.sqlite3')
            config=SimpleNamespace(notification_mqtt_user='',notification_mqtt_password='',
                notification_mqtt_host='127.0.0.1',notification_mqtt_port=server.server_address[1])
            bridge=MqttNotificationBridge(config,queue)
            try:
                bridge.start()
                deadline=time.monotonic()+5
                while time.monotonic()<deadline and not (bridge.online and queue.status()['pending']==1):
                    time.sleep(0.02)
                self.assertTrue(bridge.online)
                self.assertEqual(1,queue.status()['pending'])
                telegram=Mock();adapter=TelegramAdapter(telegram,'configured-family')
                self.assertTrue(queue.deliver_one(adapter))
                self.assertFalse(queue.deliver_one(adapter))
                telegram.send_message.assert_called_once_with('configured-family','Fridge switched off')
                bridge.publish_status()
            finally:
                bridge.stop();server.shutdown();server.server_close();thread.join(timeout=2)
            configs=[json.loads(raw) for topic,raw,retain in server.published if topic.endswith('/config')]
            self.assertEqual(2,len(configs))
            self.assertTrue(any(c.get('default_entity_id')=='notify.energyhub_family_telegram' for c in configs))
            self.assertTrue(any(topic.endswith('/availability') and raw==b'offline'
                                for topic,raw,retain in server.published))
