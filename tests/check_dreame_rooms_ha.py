import asyncio
import copy
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]


from homeassistant.components.automation.config import PLATFORM_SCHEMA
from homeassistant.components.homeassistant.triggers import state, homeassistant, event
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.components.light.reproduce_state import async_reproduce_states
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers.script import Script
from homeassistant.helpers.script_variables import ScriptVariables
from homeassistant.helpers.selector import selector
from homeassistant.helpers.entity import entity_sources
from homeassistant.util.yaml import load_yaml


async def main():
    hass = HomeAssistant(str(WORK / 'ha-test-config'))
    blueprint = Blueprint(
        load_yaml(WORK / 'dreame_room_lights.yaml'),
        expected_domain='automation', schema=BLUEPRINT_SCHEMA,
    )
    inputs = {
        'vacuum': 'vacuum.robot',
        'room_bindings': [
            {'room': ' КУХНЯ ', 'lights': ['light.kitchen'], 'brightness': 60, 'mode': 'rgb', 'color': [1, 2, 3]},
            {'room': 'Офис', 'lights': ['light.office'], 'mode': 'temperature', 'temperature': 2700},
        ],
        'room_delay': 0,
    }
    for name, value in inputs.items():
        selector(blueprint.inputs[name]['selector'])(value)
    supplied = BlueprintInputs(blueprint, {'id': 'test', 'alias': 'test', 'use_blueprint': {'path': 'test.yaml', 'input': inputs}})
    supplied.validate()
    validated = PLATFORM_SCHEMA(supplied.async_substitute())
    for trigger in validated['triggers']:
        if trigger['platform'] == 'state':
            await state.async_validate_trigger_config(hass, trigger)
        elif trigger['platform'] == 'event':
            event.TRIGGER_SCHEMA(trigger)
        else:
            homeassistant.TRIGGER_SCHEMA(trigger)
    print('PASS: actual HA 2026.10.4 blueprint, selectors, input substitution, automation/action schemas')

    attrs = dict(docked=True, current_segment=1, selected_map='Первый этаж', selected_map_id=1,
                 rooms={'Первый этаж': [{'id': 1, 'name': 'Офис'}, {'id': 6, 'name': 'Кухня'}, {'id': 5, 'name': 'Гостиная'}]})
    hass.states.async_set('vacuum.robot', 'docked', attrs)
    hass.states.async_set('light.kitchen', 'off', {'brightness': 30, 'rgb_color': [255, 0, 0]})
    hass.states.async_set('light.office', 'on', {'brightness': 150, 'color_temp_kelvin': 4000})
    hass.states.async_set('automation.test', 'on')
    original = {entity: hass.states.get(entity).as_dict() for entity in ['light.kitchen', 'light.office']}
    snapshots = {}
    calls = []
    notifications = []
    save_delay = 0
    device_memory = {}
    probe_delay = 0
    probe_reports = True
    probe_started = asyncio.Event()

    async def create_scene(call):
        if save_delay:
            await asyncio.sleep(save_delay)
        entity = 'scene.' + call.data['scene_id']
        snapshots[entity] = {light: hass.states.get(light) for light in call.data['snapshot_entities']}
        hass.states.async_set(entity, 'unknown', {'entity_id': list(snapshots[entity])})
        calls.append(('save', entity))

    async def restore_scene(call):
        entities = call.data['entity_id']
        for entity in [entities] if isinstance(entities, str) else entities:
            for light, state in snapshots[entity].items():
                if light in device_memory:
                    # Exercise HA's real off reproduction: it only calls turn_off,
                    # leaving the lamp's internal color/brightness untouched.
                    await async_reproduce_states(hass, [state], context=Context())
                else:
                    hass.states.async_set(light, state.state, dict(state.attributes))
            calls.append(('restore', entity))

    async def delete_scene(call):
        entities = call.data['entity_id']
        for entity in [entities] if isinstance(entities, str) else entities:
            del snapshots[entity]
            hass.states.async_remove(entity)

    async def light_on(call):
        entities = call.data['entity_id']
        for entity in [entities] if isinstance(entities, str) else entities:
            if entity in device_memory:
                attributes = dict(device_memory[entity])
                data = {key: value for key, value in call.data.items() if key != 'entity_id'}
                if not data and hass.states.is_state(entity, 'off'):
                    probe_started.set()
                    # Simulate a device acknowledging on before its attributes.
                    hass.states.async_set(entity, 'on', dict(hass.states.get(entity).attributes))
                    if probe_reports:
                        hass.loop.call_later(probe_delay, hass.states.async_set, entity, 'on', attributes)
                    calls.append(('on', entity))
                    continue
                if 'brightness_pct' in data:
                    data['brightness'] = round(data.pop('brightness_pct') * 255 / 100)
                if 'color_temp_kelvin' in data:
                    attributes.pop('rgb_color', None)
                    attributes['color_mode'] = 'color_temp'
                elif 'rgb_color' in data:
                    attributes.pop('color_temp_kelvin', None)
                    attributes['color_mode'] = 'rgb'
                attributes.update(data)
                device_memory[entity] = attributes
                hass.states.async_set(entity, 'on', attributes)
                calls.append(('on', entity))
                continue
            attributes = dict(hass.states.get(entity).attributes)
            attributes.update({key: value for key, value in call.data.items() if key != 'entity_id'})
            hass.states.async_set(entity, 'on', attributes)
            calls.append(('on', entity))

    async def light_off(call):
        entities = call.data['entity_id']
        for entity in [entities] if isinstance(entities, str) else entities:
            # OFF hides parameters, but the hardware keeps its latest values.
            hass.states.async_set(entity, 'off', {
                'supported_color_modes': device_memory[entity]['supported_color_modes'],
                'color_mode': None, 'brightness': None,
            })
            calls.append(('off', entity))

    async def notification(call):
        notifications.append(call.data['message'])

    hass.services.async_register('scene', 'create', create_scene)
    hass.services.async_register('scene', 'turn_on', restore_scene)
    hass.services.async_register('scene', 'delete', delete_scene)
    hass.services.async_register('light', 'turn_on', light_on)
    hass.services.async_register('light', 'turn_off', light_off)
    hass.services.async_register('persistent_notification', 'create', notification)

    async def automation_on(call):
        for entity in call.data['entity_id']:
            hass.states.async_set(entity, 'on')
            calls.append(('resume', entity))

    async def automation_off(call):
        assert call.data['stop_actions'] is True
        for entity in call.data['entity_id']:
            hass.states.async_set(entity, 'off')
            calls.append(('pause', entity))

    hass.services.async_register('automation', 'turn_on', automation_on)
    hass.services.async_register('automation', 'turn_off', automation_off)

    automation = Script(hass, validated['actions'], 'Dreame test', 'automation',
                        variables=validated['variables'], script_mode='queued', max_runs=2)

    async def run(manual=False):
        return await automation.async_run(
            {'this': hass.states.get('automation.test'), 'trigger': {'platform': None if manual else 'state'}},
            Context(),
        )

    def update(**changes):
        attrs.update(changes)
        hass.states.async_set('vacuum.robot', 'cleaning' if not attrs['docked'] else 'docked', dict(attrs))

    def restored(entity):
        actual = hass.states.get(entity)
        expected = original[entity]
        return actual.state == expected['state'] and dict(actual.attributes) == dict(expected['attributes'])

    await run(manual=True)
    assert not calls and 'Кухня' in notifications[-1] and 'найдена' in notifications[-1]
    print('PASS: manual action shows live room names and mappings, does not change lights')

    update(docked=False, current_segment=6)
    await run()
    assert hass.states.get('light.kitchen').attributes['brightness_pct'] == 60
    assert hass.states.get('light.kitchen').attributes['rgb_color'] == [1, 2, 3]
    saved_count = sum(kind == 'save' for kind, _ in calls)
    await run()
    assert sum(kind == 'save' for kind, _ in calls) == saved_count
    update(current_segment=1)
    await run()
    assert restored('light.kitchen')
    assert calls[-3][0] == 'restore' and calls[-1] == ('on', 'light.office')
    assert hass.states.get('light.office').attributes['color_temp_kelvin'] == 2700
    update(docked=True)
    await run()
    assert restored('light.kitchen') and restored('light.office') and not snapshots
    print('PASS: multi-room switch restores old before changing new, distinct colors, no snapshot overwrite, base cleanup')

    update(docked=False, current_segment=6)
    await run()
    update(current_segment=5)
    await run()
    assert restored('light.kitchen') and not snapshots
    print('PASS: transition to an unconfigured room restores previous light')

    update(current_segment=6)
    await run()
    attrs['rooms'] = {'Второй этаж': [{'id': 6, 'name': 'Офис'}]}
    update(selected_map='Второй этаж', selected_map_id=2)
    await run()
    assert restored('light.kitchen') and hass.states.get('light.office').attributes['color_temp_kelvin'] == 2700
    update(docked=True)
    await run()
    print('PASS: names resolved from active map rather than hardcoded room or map IDs')

    attrs['rooms'] = {'Первый этаж': [{'id': 1, 'name': 'Офис'}, {'id': 6, 'name': 'Кухня'}]}
    update(docked=False, selected_map='Первый этаж', selected_map_id=1, current_segment=6)
    await run()
    hass.states.async_set('vacuum.robot', 'unavailable', dict(attrs))
    await run()
    assert restored('light.kitchen') and not snapshots
    print('PASS: unavailable robot restores light')

    # Exercise real HA wait_template/event tracking. Restart timer on boundary
    # changes; arrival at the dock bypasses the remaining timeout.
    automation.variables = ScriptVariables({**validated['variables'].variables, 'settle_seconds': 0.15})
    update(docked=False, current_segment=6)
    before = len(calls)
    task = asyncio.create_task(run())
    await asyncio.sleep(0.04)
    update(current_segment=1)
    await asyncio.sleep(0.04)
    update(current_segment=6)
    await asyncio.sleep(0.08)
    assert len(calls) == before, calls[before:]
    await task
    assert calls[-1] == ('on', 'light.kitchen')
    before = len(calls)
    update(current_segment=1)
    task = asyncio.create_task(run())
    await asyncio.sleep(0.03)
    update(docked=True)
    await asyncio.wait_for(task, timeout=0.1)
    assert restored('light.kitchen') and not snapshots
    assert all(kind != 'on' for kind, _ in calls[before:])
    print('PASS: actual HA debounce resets across adjacent rooms; dock interrupts wait immediately')

    update(docked=False, current_segment=6)
    await run()
    before = len(calls)
    update(current_segment=1)
    task = asyncio.create_task(run())
    await asyncio.sleep(0.04)
    update(current_segment=6)
    await task
    assert len(calls) == before and snapshots
    update(docked=True)
    await run()
    assert restored('light.kitchen') and not snapshots
    print('PASS: active-room boundary bounce preserves both the applied light and original snapshot')

    automation.variables = ScriptVariables(validated['variables'].variables)
    save_delay = 0.05
    before = len(calls)
    update(docked=False, current_segment=6)
    first = asyncio.create_task(run())
    await asyncio.sleep(0.02)
    update(docked=True)
    second = asyncio.create_task(run())
    await asyncio.gather(first, second)
    assert not snapshots and restored('light.kitchen')
    assert all(kind != 'on' for kind, _ in calls[before:])
    save_delay = 0
    print('PASS: docking during asynchronous snapshot creation does not turn on stale room light')

    # A typo is visible in manual diagnosis, including available names.
    automation.variables = ScriptVariables({**validated['variables'].variables, 'configured_rooms': [{'room': 'Typo', 'lights': ['light.kitchen']}]})
    await run(manual=True)
    assert 'НЕ НАЙДЕНА' in notifications[-1] and 'Кухня' in notifications[-1]
    print('PASS: typo diagnosis offers actual names without developer tools')

    automation.variables = ScriptVariables({**validated['variables'].variables, 'configured_rooms': [
        {'room': 'Кухня', 'lights': ['light.kitchen']}, {'room': 'Офис', 'lights': ['light.kitchen']},
    ]})
    update(docked=False, current_segment=6)
    before = len(calls)
    await run()
    assert len(calls) == before and 'Уберите повторяющиеся' in notifications[-1]
    print('PASS: duplicate lamps are rejected with an actionable notification')
    # Solar rules gate new light overrides and the corresponding automation
    # pauses. Cleanup must remain independent of the sun after entry.
    hass.states.async_set('light.kitchen', original['light.kitchen']['state'],
        dict(original['light.kitchen']['attributes']))
    hass.states.async_set('automation.motion', 'on')
    for rule, sun, allowed in [
        ('below_horizon', 'above_horizon', False),
        ('below_horizon', 'below_horizon', True),
        ('above_horizon', 'below_horizon', False),
        ('above_horizon', 'above_horizon', True),
        ('below_horizon', 'unavailable', False),
        ('always', 'unavailable', True),
    ]:
        solar_rooms = [{'room': 'Кухня', 'lights': ['light.kitchen'],
                        'automations': ['automation.motion'], 'sun_condition': rule}]
        selector(blueprint.inputs['room_bindings']['selector'])(solar_rooms)
        automation.variables = ScriptVariables({**validated['variables'].variables,
            'configured_rooms': solar_rooms})
        hass.states.async_set('sun.sun', sun)
        update(docked=False, current_segment=6)
        before = len(calls)
        await run()
        if allowed:
            assert hass.states.is_state('automation.motion', 'off') and snapshots
            assert hass.states.is_state('light.kitchen', 'on')
            hass.states.async_set('sun.sun', 'below_horizon' if sun == 'above_horizon' else 'above_horizon')
            await run()
            assert snapshots and hass.states.is_state('automation.motion', 'off')
        else:
            assert len(calls) == before and not snapshots
            assert hass.states.is_state('automation.motion', 'on')
        update(docked=True)
        await run()
        assert not snapshots and restored('light.kitchen')
        assert hass.states.is_state('automation.motion', 'on')
    print('PASS: solar rules above/below/always, unavailable sun, blocked-entry no-op and unconditional cleanup')

    selector(blueprint.inputs['sun_entity']['selector'])('sun.alternative')
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'sun_entity': 'sun.alternative', 'configured_rooms': [
            {'room': 'Кухня', 'lights': ['light.kitchen'], 'sun_condition': 'below_horizon'}]})
    hass.states.async_set('sun.sun', 'below_horizon')
    hass.states.async_set('sun.alternative', 'above_horizon')
    update(docked=False, current_segment=6)
    before = len(calls)
    await run()
    assert len(calls) == before and not snapshots
    hass.states.async_set('sun.sun', 'above_horizon')
    hass.states.async_set('sun.alternative', 'below_horizon')
    await run()
    assert snapshots and hass.states.is_state('light.kitchen', 'on')
    update(docked=True)
    await run()
    assert restored('light.kitchen') and not snapshots
    print('PASS: selected sun entity controls lighting even when sun.sun has opposite state')

    # Attach actual HA triggers, rather than only calling the script manually.
    # The selected room sensor is authoritative even if vacuum attributes lag.
    selector(blueprint.inputs['current_room_sensor']['selector'])('sensor.room')
    selector(blueprint.inputs['robot_state_sensor']['selector'])('sensor.robot_state')
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'room_sensor': 'sensor.room', 'state_sensor': 'sensor.robot_state'})
    update(docked=False, current_segment=6)
    hass.states.async_set('vacuum.robot', 'paused', dict(attrs))
    hass.states.async_set('sensor.room', 'Офис')
    hass.states.async_set('sensor.robot_state', 'paused')
    fired = []

    async def triggered(variables, context):
        fired.append(variables['trigger']['id'])
        await automation.async_run({'this': hass.states.get('automation.test'), **variables}, context)

    unsubscribers = []
    for index in range(3):
        trigger = validated['triggers'][index]
        module = state if index == 0 else event
        trigger_config = (await state.async_validate_trigger_config(hass, trigger)
                          if index == 0 else event.TRIGGER_SCHEMA(trigger))
        info = {'trigger_data': {'id': str(index), 'idx': str(index)},
                'variables': {'selected_room_sensor': 'sensor.room',
                              'selected_state_sensor': 'sensor.robot_state'}}
        unsubscribers.append(await module.async_attach_trigger(hass, trigger_config, triggered, info))
    hass.states.async_set('vacuum.robot', 'cleaning', dict(attrs))
    await hass.async_block_till_done()
    assert '0' in fired and hass.states.is_state('light.office', 'on')
    assert hass.states.get('light.office').attributes['color_temp_kelvin'] == 2700
    hass.states.async_set('sensor.robot_state', 'mopping')
    await hass.async_block_till_done()
    assert '2' in fired
    hass.states.async_set('sensor.room', 'Кухня')
    await hass.async_block_till_done()
    assert '1' in fired and restored('light.office')
    assert hass.states.is_state('light.kitchen', 'on')
    before = len(calls)
    hass.states.async_set('sensor.room', 'Кухня', {'room_id': 6})
    await hass.async_block_till_done()
    assert len(calls) == before
    update(docked=True)
    await hass.async_block_till_done()
    assert not snapshots and restored('light.kitchen')
    for unsubscribe in unsubscribers:
        unsubscribe()
    print('PASS: real vacuum-state and sensor-event triggers; same-room resume; sensor overrides stale map; attribute-only no-op; dock cleanup')

    # Reproduce the real trace: three selected light groups expand to nine
    # lamps with different original states. Snapshot and restore the members.
    group_ids = []
    member_original = {}
    for group_index in range(3):
        members = []
        for member_index in range(3):
            entity = f'light.group_{group_index}_member_{member_index}'
            members.append(entity)
            hass.states.async_set(entity, 'off' if member_index == 2 else 'on',
                {'brightness': 40 + group_index * 20 + member_index,
                 'color_temp_kelvin': 2700 + member_index * 500})
            member_original[entity] = hass.states.get(entity)
        group = f'light.room_group_{group_index}'
        group_ids.append(group)
        entity_sources(hass)[group] = {'domain': 'group'}
        hass.states.async_set(group, 'on', {'entity_id': members})
    group_rooms = [{'room': 'Офис', 'lights': group_ids, 'brightness': 100,
                    'mode': 'temperature', 'temperature': 6500}]
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': group_rooms})
    update(docked=False, current_segment=1)
    await run()
    assert len(snapshots) == 2
    assert set(next(value for key, value in snapshots.items() if not key.endswith('_off_parameters'))) == set(member_original)
    assert set(next(value for key, value in snapshots.items() if key.endswith('_off_parameters'))) == {
        member for member, previous in member_original.items() if previous.state == 'off'}
    for member in member_original:
        assert hass.states.is_state(member, 'on')
        assert hass.states.get(member).attributes['brightness_pct'] == 100
        assert hass.states.get(member).attributes['color_temp_kelvin'] == 6500
    await run()
    assert len(snapshots) == 2
    update(docked=True)
    await run()
    assert not snapshots
    for member, previous in member_original.items():
        current = hass.states.get(member)
        assert current.state == previous.state and current.attributes == previous.attributes
    print('PASS: three groups with nine lamps receive 100%/6500K and restore each member separately')

    overlap = group_rooms + [{'room': 'Кухня', 'lights': [next(iter(member_original))]}]
    automation.variables = ScriptVariables({**validated['variables'].variables, 'configured_rooms': overlap})
    update(docked=False, current_segment=1)
    before = len(calls)
    await run()
    assert len(calls) == before and 'повторяющиеся' in notifications[-1]
    automation.variables = ScriptVariables({**validated['variables'].variables, 'configured_rooms': group_rooms})
    hass.states.async_set(next(iter(member_original)), 'unavailable')
    await run()
    assert len(calls) == before and not snapshots
    print('PASS: overlapping group membership and unavailable members cannot corrupt snapshots')

    simple_rooms = [
        {'room': 'Кухня', 'lights': ['light.kitchen'], 'automations': ['automation.motion', 'automation.shared', 'automation.test']},
        {'room': 'Офис', 'lights': ['light.office'], 'automations': ['automation.office_motion', 'automation.shared']},
    ]
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': simple_rooms})
    hass.states.async_set('automation.motion', 'on')
    hass.states.async_set('automation.office_motion', 'off')
    hass.states.async_set('automation.shared', 'on')
    update(docked=False, current_segment=6)
    await run()
    assert hass.states.is_state('automation.motion', 'off')
    assert hass.states.is_state('automation.office_motion', 'on')
    assert hass.states.is_state('automation.shared', 'off')
    assert hass.states.is_state('automation.test', 'on')
    update(current_segment=1)
    await run()
    assert hass.states.is_state('automation.motion', 'on')
    assert hass.states.is_state('automation.office_motion', 'off')
    assert hass.states.is_state('automation.shared', 'off')
    # Simple mode uses current position, not a saved helper or temporary marker.
    for scene in list(snapshots):
        hass.states.async_remove(scene)
    snapshots.clear()
    update(docked=True)
    await run()
    assert all(hass.states.is_state(entity, 'on') for entity in
               ['automation.motion', 'automation.office_motion', 'automation.shared'])
    print('PASS: simple helper-free pause/resume, shared automations stay paused in active room; dock resumes all even without scenes')

    hass.states.async_set('light.relay', 'off', {'supported_color_modes': ['onoff']})
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': [{'room': 'Офис', 'lights': ['light.relay']}]})
    update(docked=False, current_segment=1)
    await run()
    assert hass.states.is_state('light.relay', 'on')
    assert dict(hass.states.get('light.relay').attributes) == {'supported_color_modes': ['onoff']}
    update(docked=True)
    await run()
    assert hass.states.is_state('light.relay', 'off')
    print('PASS: room without settings sends only turn_on to smart relay and restores off')

    for overrides, expected in [
        ({'brightness': 85}, {'brightness_pct': 85}),
        ({'mode': 'temperature', 'temperature': 5700}, {'color_temp_kelvin': 5700}),
        ({'mode': 'temperature', 'temperature': 5700, 'brightness': 100},
         {'color_temp_kelvin': 5700, 'brightness_pct': 100}),
        ({'mode': 'keep', 'brightness': 100, 'temperature': 5700}, {}),
    ]:
        hass.states.async_set('light.relay', 'off')
        automation.variables = ScriptVariables({**validated['variables'].variables,
            'configured_rooms': [{'room': 'Офис', 'lights': ['light.relay'], **overrides}]})
        update(docked=False, current_segment=1)
        await run()
        assert dict(hass.states.get('light.relay').attributes) == expected
        update(docked=True)
        await run()
    print('PASS: only explicit room parameters sent; brightness/temperature combined; keep mode preserves parameters')

    automation.variables = ScriptVariables({**validated['variables'].variables,
        'settle_seconds': 30,
        'configured_rooms': [{'room': 'Офис', 'lights': ['light.office']} ]})
    update(docked=True, current_segment=1)
    docked_state = hass.states.get('vacuum.robot')
    update(docked=False)
    departure_state = hass.states.get('vacuum.robot')
    await asyncio.wait_for(automation.async_run({
        'this': hass.states.get('automation.test'),
        'trigger': {'platform': 'state', 'from_state': docked_state, 'to_state': departure_state},
    }, Context()), timeout=0.5)
    assert snapshots and hass.states.is_state('light.office', 'on')
    update(docked=True)
    await asyncio.wait_for(run(), timeout=0.5)
    assert not snapshots and restored('light.office')
    print('PASS: station departure and arrival bypass 30-second delay')

    automation.variables = ScriptVariables({**validated['variables'].variables,
        'settle_seconds': 0.15})
    update(docked=False, current_segment=6)
    before = len(calls)
    task = asyncio.create_task(automation.async_run({
        'this': hass.states.get('automation.test'),
        'trigger': {'platform': 'state', 'from_state': docked_state, 'to_state': departure_state},
    }, Context()))
    await asyncio.sleep(0.05)
    assert len(calls) == before
    await task
    assert hass.states.is_state('light.kitchen', 'on')
    update(docked=True)
    await run()
    print('PASS: stale queued departure cannot bypass delay in another room')

    # Regression at the actual HA light-reproduction boundary, with hidden OFF
    # attributes and separate hardware memory. Both RGB and warm white must
    # survive cleaning, and an already-on lamp must not be probed.
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': [{'room': 'Офис',
            'lights': ['light.hidden_white', 'light.hidden_rgb', 'light.already_on'],
            'mode': 'temperature', 'temperature': 6500, 'brightness': 100}]})
    device_memory.update({
        'light.hidden_white': {'supported_color_modes': ['color_temp'],
            'color_mode': 'color_temp', 'brightness': 37, 'color_temp_kelvin': 2700},
        'light.hidden_rgb': {'supported_color_modes': ['rgb', 'color_temp'],
            'color_mode': 'rgb', 'brightness': 81, 'rgb_color': (255, 0, 40)},
        'light.already_on': {'supported_color_modes': ['color_temp'],
            'color_mode': 'color_temp', 'brightness': 120, 'color_temp_kelvin': 4100},
    })
    hardware_original = copy.deepcopy(device_memory)
    hass.states.async_set('light.already_on', 'on', device_memory['light.already_on'])
    for entity in ['light.hidden_white', 'light.hidden_rgb']:
        hass.states.async_set(entity, 'off', {
            'supported_color_modes': device_memory[entity]['supported_color_modes'],
            'color_mode': None, 'brightness': None,
        })
    probe_delay = 0.02
    before = len(calls)
    update(docked=False, current_segment=1)
    await run()
    saved_parameters = next(value for key, value in snapshots.items() if key.endswith('_off_parameters'))
    assert set(saved_parameters) == {'light.hidden_white', 'light.hidden_rgb'}
    assert saved_parameters['light.hidden_white'].attributes['color_temp_kelvin'] == 2700
    assert saved_parameters['light.hidden_rgb'].attributes['rgb_color'] == (255, 0, 40)
    assert sum(call == ('on', 'light.already_on') for call in calls[before:]) == 1
    assert all(hass.states.is_state(entity, 'on') for entity in device_memory)
    assert all(values['color_temp_kelvin'] == 6500 for values in device_memory.values())
    update(docked=True)
    await run()
    assert device_memory == hardware_original
    assert hass.states.is_state('light.already_on', 'on')
    assert hass.states.is_state('light.hidden_white', 'off') and hass.states.is_state('light.hidden_rgb', 'off')
    assert not snapshots
    print('PASS: real HA light reproduction restores hidden OFF brightness/RGB/temperature before switching off; already-on lamp not probed')

    # Departure during probing must not leave a lamp on or apply cleaning color.
    probe_started.clear()
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': [{'room': 'Офис', 'lights': ['light.hidden_white'],
            'mode': 'temperature', 'temperature': 6500, 'brightness': 100}]})
    update(docked=False, current_segment=1)
    task = asyncio.create_task(run())
    await probe_started.wait()
    update(docked=True)
    await task
    assert hass.states.is_state('light.hidden_white', 'off')
    assert device_memory == hardware_original and not snapshots
    print('PASS: docking during initial probe rolls back original state without applying cleaning settings')

    # Device acknowledged ON but never reported its settings: do not overwrite
    # unknown hardware parameters with cleaning settings after the timeout.
    probe_reports = False
    update(docked=False, current_segment=1)
    await run()
    assert hass.states.is_state('light.hidden_white', 'off')
    assert device_memory == hardware_original and not snapshots
    print('PASS: missing probe attributes time out and restore OFF without overwriting hardware parameters')

    await automation.async_stop()
    await hass.async_stop(force=True)
    print('All checks passed using real HA schemas, templates and script engine; scene/light service endpoints mocked.')


asyncio.run(main())
