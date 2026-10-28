"""One-address transactions for the reviewed Hisense integration data format."""
import asyncio
from copy import deepcopy
from ipaddress import IPv4Address, IPv4Network


def address(value):
    ip = IPv4Address(str(value).strip())
    if not any(ip in IPv4Network(net) for net in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Use a private LAN IPv4 address')
    if int(str(ip).split('.')[-1]) in (0, 255):
        raise ValueError('Host address required')
    return str(ip)


def changed_data(data, mac, value):
    result = deepcopy(data)
    rows = result.get('devices')
    if not isinstance(rows, list):
        raise ValueError('Unsupported integration configuration')
    selected = [row for row in rows if row.get('mac_address') == mac]
    if len(selected) != 1:
        raise ValueError('Device identity is ambiguous')
    selected[0]['ip_address'] = address(value)
    return result


class Editor:
    """Persist before mutation; rollback only our own address after any failure.

    Callbacks implement the HA config-entry API and fresh authenticated status
    verification. No temperature, mode, relay or raw protocol writes here.
    """
    def __init__(self, journal, save, read, update, verify):
        self.journal = journal
        self.save = save
        self.read = read
        self.update = update
        self.verify = verify
        self.lock = asyncio.Lock()

    async def rollback(self, txn):
        current = self.read(txn['entry'])
        rows = current.get('devices', [])
        selected = [row for row in rows if row.get('mac_address') == txn['mac']]
        if len(selected) == 1 and selected[0].get('ip_address') == txn['old']:
            self.journal['status'] = 'already_restored'
            return True
        # An independent edit takes precedence. Never overwrite it.
        if len(selected) != 1 or selected[0].get('ip_address') != txn['new']:
            self.journal['status'] = 'conflict'
            return False
        self.update(txn['entry'], changed_data(current, txn['mac'], txn['old']))
        restored = await self.verify(txn['entry'], txn['mac'], txn['old'])
        self.journal['status'] = 'rolled_back' if restored else 'rollback_unverified'
        return restored

    async def recover(self):
        async with self.lock:
            if txn := self.journal.get('pending'):
                await self.rollback(txn)
                self.journal.pop('pending', None)
                await self.save(self.journal)

    async def apply(self, entry, mac, new):
        async with self.lock:
            if self.journal.get('pending'):
                raise ValueError('Resolve interrupted change first')
            current = self.read(entry)
            updated = changed_data(current, mac, new)
            old = next(row['ip_address'] for row in current['devices'] if row['mac_address'] == mac)
            address(old)
            if old == address(new):
                return False
            txn = dict(entry=entry, mac=mac, old=old, new=address(new))
            self.journal.update(pending=txn, status='verifying')
            await self.save(self.journal)
            finalized = False
            try:
                latest = self.read(entry)
                row = next(row for row in latest['devices'] if row['mac_address'] == mac)
                if row['ip_address'] != old:
                    raise ValueError('Address changed independently before applying')
                updated = changed_data(latest, mac, new)
                self.update(entry, updated)
                if not await self.verify(entry, mac, txn['new']):
                    raise ValueError('No fresh authenticated heat-pump status at new address')
                # Detect a concurrent independent config edit during verification.
                row = next(row for row in self.read(entry)['devices'] if row['mac_address'] == mac)
                if row['ip_address'] != txn['new']:
                    raise ValueError('Address changed independently during verification')
                self.journal['status'] = 'verified'
                finalized = True
            except (Exception, asyncio.CancelledError):
                await self.rollback(txn)
                finalized = True
                raise
            finally:
                if finalized:
                    self.journal.pop('pending', None)
                await self.save(self.journal)
            return True
