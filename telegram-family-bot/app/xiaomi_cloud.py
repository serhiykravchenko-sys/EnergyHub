"""Fresh, read-only Xiaomi availability using an existing HA session.

Never logs credentials, refreshes authentication or controls a device.
"""
import base64
import hashlib
import json
import os
import struct
import time
from pathlib import Path
from urllib import request, parse


class RC4:
    def __init__(self, key):
        self.s=list(range(256)); j=0
        for i in range(256):
            j=(j+self.s[i]+key[i%len(key)])%256
            self.s[i],self.s[j]=self.s[j],self.s[i]
        self.i=self.j=0
        self.crypt(bytes(1024))

    def crypt(self, data):
        if isinstance(data,str): data=data.encode()
        output=bytearray()
        for value in data:
            self.i=(self.i+1)%256; self.j=(self.j+self.s[self.i])%256
            self.s[self.i],self.s[self.j]=self.s[self.j],self.s[self.i]
            output.append(value ^ self.s[(self.s[self.i]+self.s[self.j])%256])
        return bytes(output)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Xiaomi redirect refused')


def read(entity, root=Path('/homeassistant/.storage')):
    """Resolve identity through HA registry; cached online values are ignored."""
    registry=json.loads((root/'core.entity_registry').read_text(encoding='utf-8'))['data']['entities']
    row=next(x for x in registry if x['entity_id']==entity)
    entries=json.loads((root/'core.config_entries').read_text(encoding='utf-8'))['data']['entries']
    entry=next(x for x in entries if x['entry_id']==row['config_entry_id'])
    if entry['domain']!='xiaomi_miot': raise ValueError('Unexpected integration')
    cfg=entry['data']; region=cfg.get('server_country')
    if region not in {'cn','de','us','ru','sg','i2'}: raise ValueError('Unknown Xiaomi region')
    auth_path=root/'xiaomi_miot'/f"auth-{cfg['user_id']}-{region}.json"
    auth=json.loads(auth_path.read_text(encoding='utf-8'))['data'] if auth_path.exists() else cfg
    if str(auth.get('user_id'))!=str(cfg['user_id']) or auth.get('sid','xiaomiio')!='xiaomiio':
        raise ValueError('Session mismatch')
    if not all(auth.get(k) for k in ('service_token','ssecurity','user_id')):
        raise ValueError('Existing session unavailable')
    cache=json.loads((root/'xiaomi_miot'/f"devices-{cfg['user_id']}-{region}.json").read_text(encoding='utf-8'))['data']
    devices=json.loads((root/'core.device_registry').read_text(encoding='utf-8'))['data']['devices']
    device=next(x for x in devices if x['id']==row['device_id'])
    identities={str(v).lower() for _,v in device.get('identifiers',[])}
    macs={str(v).replace(':','').lower() for _,v in device.get('connections',[])}
    def matches(d):
        mac=str(d.get('mac','')).replace(':','').lower()
        return str(d.get('did')) in identities or (len(mac)==12 and
            (mac in macs or any(mac in value.replace(':','') for value in identities)))
    targets=[d for d in cache['devices'] if matches(d)]
    if len(targets)!=1 or targets[0].get('model')!='lumi.gateway.v3':
        raise ValueError('Hub identity unconfirmed')
    target=targets[0]
    host='api.io.mi.com' if region=='cn' else f'{region}.api.io.mi.com'
    nonce=base64.b64encode(os.urandom(8)+struct.pack('>I',int(time.time()/60))).decode()
    key=hashlib.sha256(base64.b64decode(auth['ssecurity'])+base64.b64decode(nonce)).digest()
    signed=base64.b64encode(key).decode()
    def signature(params):
        pieces=['POST','/home/device_list']+[f'{k}={v}' for k,v in params.items()]+[signed]
        return base64.b64encode(hashlib.sha1('&'.join(pieces).encode()).digest()).decode()
    params={'data':json.dumps(dict(getVirtualModel=True,getHuamiDevices=1,
                get_split_device=False,support_smart_home=True),separators=(',',':'))}
    params['rc4_hash__']=signature(params)
    params={k:base64.b64encode(RC4(key).crypt(v)).decode() for k,v in params.items()}
    params.update(signature=signature(params),ssecurity=auth['ssecurity'],_nonce=nonce)
    cookies=dict(userId=str(auth['user_id']),yetAnotherServiceToken=auth['service_token'],
                 serviceToken=auth['service_token'],locale='en_GB',timezone='GMT+03:00',
                 is_daylight='1',dst_offset='3600000',channel='MI_APP_STORE')
    headers={'Content-Type':'application/x-www-form-urlencoded',
             'User-Agent':'Android-7.1.1-1.0.0-ONEPLUS A3010-136-'+str(auth.get('device_id') or os.urandom(8).hex())+' APP/xiaomi.smarthome APPV/62830',
             'X-XIAOMI-PROTOCAL-FLAG-CLI':'PROTOCAL-HTTP2',
             'MIOT-ENCRYPT-ALGORITHM':'ENCRYPT-RC4','Accept-Encoding':'identity',
             'Cookie':'; '.join(f'{k}={v}' for k,v in cookies.items())}
    req=request.Request(f'https://{host}/app/home/device_list',data=parse.urlencode(params).encode(),headers=headers,method='POST')
    with request.build_opener(NoRedirect()).open(req,timeout=20) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000: raise ValueError('Response limit')
    try: decoded=json.loads(raw)
    except (ValueError,UnicodeError): decoded=json.loads(RC4(key).crypt(base64.b64decode(raw)))
    if decoded.get('code')!=0: raise ValueError('Cloud session/request rejected')
    hub=next((d for d in decoded.get('result',{}).get('list',[]) if d.get('did')==target['did']),None)
    if not hub or not isinstance(hub.get('isOnline'),bool): raise ValueError('Fresh hub status unavailable')
    return hub['isOnline']
