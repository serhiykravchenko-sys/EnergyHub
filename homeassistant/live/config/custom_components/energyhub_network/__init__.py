"""Reviewed integration adapter. Endpoint changes require an HA administrator."""
import asyncio
from datetime import timedelta
from datetime import datetime, timezone
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import callback
from homeassistant.helpers import entity_registry, device_registry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from .endpoint import Editor
from .health import helper_update, probe

DOMAIN = 'energyhub_network'


async def async_setup(hass, config):
    store = Store(hass, 1, DOMAIN)
    journal = await store.async_load() or {}
    previous_controllers = {}
    previous_address = None
    health_lock = asyncio.Lock()

    def hp_address():
        entity = entity_registry.async_get(hass).async_get('climate.first_floor_heat_pump')
        entry = hass.config_entries.async_get_entry(entity.config_entry_id) if entity else None
        if entry is None or entry.domain != 'hisense_aircon':
            return None
        dev = device_registry.async_get(hass).async_get(entity.device_id) if entity.device_id else None
        identifiers = {str(value).replace(':', '').replace('-', '').lower()
                       for domain, value in dev.identifiers if domain == 'hisense_aircon'} if dev else set()
        matches = [row for row in entry.data.get('devices', [])
                   if str(row.get('mac_address', '')).replace(':', '').replace('-', '').lower() in identifiers]
        return matches[0].get('ip_address') if len(matches) == 1 else None

    async def check_health(_now=None):
        nonlocal previous_address
        if health_lock.locked():
            return
        async with health_lock:
            ip = hp_address()
            helper = hass.states.get('input_text.energyhub_heat_pump_proposed_address')
            value = helper_update(ip, helper.state if helper else None, previous_address)
            if value and helper and hass.services.has_service('input_text', 'set_value'):
                await hass.services.async_call('input_text', 'set_value',
                    {'entity_id': helper.entity_id, 'value': value}, blocking=True)
            previous_address = ip
            reachable = await probe(ip)
            if hp_address() != ip:
                reachable = 'unknown'
                ip = hp_address()
            hp = hass.states.get('climate.first_floor_heat_pump')
            grid = hass.states.get('sensor.powmr_10_2m_grid_voltage')
            fresh = hass.states.get('sensor.energyhub_telemetry_freshness')
            now = datetime.now(timezone.utc)
            try:
                grid_present = (float(grid.state) > 180 if grid and fresh and fresh.state == 'fresh'
                    and 0 <= now.timestamp()-grid.last_reported.timestamp() <= 30 else None)
            except (ValueError, TypeError):
                grid_present = None
            hass.states.async_set('sensor.energyhub_hp1_connection', reachable, {
                'friendly_name': 'First-floor HP connection diagnostics',
                'configured_ip': ip, 'checked_at': now.isoformat(),
                'hp_state': hp.state if hp else 'unknown',
                'ha_temperature_unit': getattr(hass.config.units.temperature_unit, 'value', hass.config.units.temperature_unit),
                'grid_present': grid_present,
                'coverage': 'One configured IP; ICMP reachability does not verify device identity or authenticated control'})

    def read(entry_id):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != 'hisense_aircon':
            raise ValueError('Supported integration entry not found')
        return dict(entry.data)

    def update(entry_id, data):
        entry = hass.config_entries.async_get_entry(entry_id)
        previous_controllers[entry_id] = hass.data.get('hisense_aircon', {}).get(entry_id)
        hass.config_entries.async_update_entry(entry, data=data)
        # Hisense's existing update listener reloads this entry once.

    async def verify(entry_id, mac, ip):
        for _ in range(60):
            controller = hass.data.get('hisense_aircon', {}).get(entry_id)
            device = controller.get_device(mac) if controller else None
            if (device and controller is not previous_controllers.get(entry_id)
                    and device.ip_address == ip):
                names = [device.topics.get('env_temp'), device.topics.get('temp')]
                names = [name for name in names if name]
                if names and all(device.has_reported_property(name) for name in names):
                    return True
            await asyncio.sleep(1)
        return False

    editor = Editor(journal, store.async_save, read, update, verify)
    # Interrupted transactions recover conservatively before accepting edits.

    @callback
    def publish(_now=None):
        addresses = {}
        for entry in hass.config_entries.async_entries('hisense_aircon'):
            for row in entry.data.get('devices', []):
                addresses[f"{entry.entry_id}:{row.get('name', 'Heat pump')}"] = row.get('ip_address', '')
        for entry in hass.config_entries.async_entries('esphome'):
            host = entry.data.get('host')
            if isinstance(host, str) and host:
                addresses[f'{entry.entry_id}:{entry.title} (ESPHome)'] = host
        hass.states.async_set('sensor.energyhub_network_inventory', journal.get('status', 'ready'),
            {'friendly_name': 'Configured device addresses', 'addresses': addresses,
             'coverage': 'Hisense configured addresses; HA/ESPHome use their native network settings'})

    async def recover(_event=None):
        try:
            await editor.recover()
        except Exception:
            journal['status'] = 'recovery_failed'
            # Keep the durable pending transaction; edits remain blocked.
        finally:
            publish()

    if journal.get('pending'):
        journal['status'] = 'recovering'
        if hass.is_running:
            hass.async_create_task(recover())
        else:
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, recover)

    async def apply(call):
        if not call.context.user_id:
            raise ServiceValidationError('An attended administrator request is required')
        if not call.data['entity_id'].startswith('climate.'):
            raise ServiceValidationError('Select a supported heat-pump climate entity')
        registry = entity_registry.async_get(hass)
        entity = registry.async_get(call.data['entity_id'])
        entry = hass.config_entries.async_get_entry(entity.config_entry_id) if entity else None
        if entry is None or entry.domain != 'hisense_aircon':
            raise ServiceValidationError('This entity has no supported address adapter')
        dev = device_registry.async_get(hass).async_get(entity.device_id) if entity.device_id else None
        identifiers = {str(value).replace(':', '').replace('-', '').lower()
                       for domain, value in dev.identifiers if domain == 'hisense_aircon'} if dev else set()
        rows = entry.data.get('devices', [])
        matches = [row for row in rows if str(row.get('mac_address', '')).replace(':', '').lower() in identifiers]
        if len(matches) != 1:
            raise ServiceValidationError('Cannot uniquely identify the configured device')
        try:
            journal['status'] = 'verifying'
            publish()
            changed = await editor.apply(entry.entry_id, matches[0]['mac_address'], call.data['address'])
            if not changed:
                journal['status'] = 'unchanged'
        except ValueError as exc:
            if journal.get('status') == 'verifying':
                journal['status'] = 'rejected'
            raise ServiceValidationError(str(exc)) from None
        finally:
            await store.async_save(journal)
            publish()

    async_register_admin_service(hass, DOMAIN, 'apply_address', apply,
        schema=vol.Schema({vol.Required('entity_id'): str, vol.Required('address'): str}))
    publish()
    async def tick(now):
        publish()
        await check_health(now)
    cancel = async_track_time_interval(hass, tick, timedelta(seconds=60))
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, check_health)
    if hass.is_running:
        hass.async_create_task(check_health())
    hass.data[DOMAIN] = {'editor': editor, 'cancel': cancel}
    return True
