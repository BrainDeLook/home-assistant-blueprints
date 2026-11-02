import asyncio
import copy
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]


from homeassistant.components.automation.config import PLATFORM_SCHEMA
from homeassistant.components.homeassistant.triggers import state, homeassistant
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import Context, HomeAssistant, State
from homeassistant.helpers.script import Script
from homeassistant.helpers.script_variables import ScriptVariables
from homeassistant.helpers.selector import selector
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
            {'room': ' КУХНЯ ', 'lights': ['light.kitchen'], 'brightness': 60, 'color': [1, 2, 3]},
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
            attributes = dict(hass.states.get(entity).attributes)
            attributes.update({key: value for key, value in call.data.items() if key != 'entity_id'})
            hass.states.async_set(entity, 'on', attributes)
            calls.append(('on', entity))

    async def notification(call):
        notifications.append(call.data['message'])

    hass.services.async_register('scene', 'create', create_scene)
    hass.services.async_register('scene', 'turn_on', restore_scene)
    hass.services.async_register('scene', 'delete', delete_scene)
    hass.services.async_register('light', 'turn_on', light_on)
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

    async def journal_write(call):
        value = call.data['value']
        entity = call.data['entity_id']
        assert len(value) <= hass.states.get(entity).attributes['max']
        hass.states.async_set(entity, value, {'max': 255})

    hass.services.async_register('automation', 'turn_on', automation_on)
    hass.services.async_register('automation', 'turn_off', automation_off)
    hass.services.async_register('input_text', 'set_value', journal_write)

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
    # Optional automation pausing: preserve off states, survive lost scenes,
    # reject corrupt/shared journals and do not pause the controlling automation.
    rooms = [
        {'room': 'Кухня', 'lights': ['light.kitchen'], 'automations': ['automation.motion', 'automation.already_off', 'automation.test']},
        {'room': 'Офис', 'lights': ['light.office'], 'automations': ['automation.motion']},
    ]
    selector(blueprint.inputs['room_bindings']['selector'])(rooms)
    selector(blueprint.inputs['automation_journal']['selector'])('input_text.restore')
    automation.variables = ScriptVariables({**validated['variables'].variables,
        'configured_rooms': rooms, 'restore_helper': 'input_text.restore'})
    hass.states.async_set('input_text.restore', '', {'max': 255})
    hass.states.async_set('automation.motion', 'on')
    hass.states.async_set('automation.already_off', 'off')
    update(docked=False, current_segment=6)
    before = len(calls)
    await run(manual=True)
    assert len(calls) == before and hass.states.is_state('automation.motion', 'on')
    await run()
    assert hass.states.is_state('automation.motion', 'off')
    assert hass.states.is_state('automation.already_off', 'off')
    assert hass.states.is_state('automation.test', 'on')
    first_record = hass.states.get('input_text.restore').state
    await run()
    assert hass.states.get('input_text.restore').state == first_record
    assert hass.states.is_state('automation.motion', 'off')
    update(current_segment=1)
    await run()
    assert hass.states.is_state('automation.motion', 'off')
    update(docked=True)
    await run()
    assert hass.states.is_state('automation.motion', 'on')
    assert hass.states.is_state('automation.already_off', 'off')
    assert hass.states.is_state('input_text.restore', '{}')
    print('PASS: per-room automation pause, initial off preserved, shared automation transition, self exclusion, manual no-op')

    update(docked=False, current_segment=6)
    await run()
    # A restart drops dynamic scenes, while input_text restores its saved value.
    for entity in list(snapshots):
        hass.states.async_remove(entity)
    snapshots.clear()
    await run()
    assert hass.states.is_state('automation.motion', 'off')
    update(docked=True)
    await run()
    assert hass.states.is_state('automation.motion', 'on')
    assert hass.states.is_state('automation.already_off', 'off')
    print('PASS: saved automation journal restores even after dynamic light scenes are lost')

    update(docked=False, current_segment=6)
    for value in ('not JSON', '{"owner":"automation.someone_else","room":"kitchen","entities":["automation.motion"]}'):
        hass.states.async_set('input_text.restore', value, {'max': 255})
        before = len(calls)
        await run()
        assert len(calls) == before and hass.states.is_state('automation.motion', 'on')
    hass.states.async_set('input_text.restore', '{}', {'max': 10})
    before = len(calls)
    await run()
    assert len(calls) == before and hass.states.is_state('automation.motion', 'on')
    assert 'не помещается' in notifications[-1]
    print('PASS: invalid journal, reused helper and capacity limit stop before pausing anything')

    await automation.async_stop()
    await hass.async_stop(force=True)
    print('All checks passed using real HA schemas, templates and script engine; scene/light service endpoints mocked.')


asyncio.run(main())
