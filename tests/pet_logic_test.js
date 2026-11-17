const fs = require('fs');
const vm = require('vm');
const path = require('path');

const file = path.resolve('web/js/pet.js');
let source = fs.readFileSync(file, 'utf8');
source = source.replace(/^import .*$/gm, '');
source = source.replace('export const PetCompanion', 'const PetCompanion');
source += '\nmodule.exports = PetCompanion;';

const fmt = {
  time: () => '23:00',
  countdown: () => '1 小时',
};
const sandbox = {
  module: { exports: {} },
  exports: {},
  fmt,
  buildPetChatter: () => ({}),
  buildPetInteraction: () => ({}),
  Date,
  Math,
  console,
  setTimeout,
  clearTimeout,
};
vm.runInNewContext(source, sandbox, { filename: file });
const pet = sandbox.module.exports;
const m = pet.methods;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(typeof m.isLateNight === 'function', 'isLateNight must be a method');
assert(typeof m.nightSleepEligible === 'function', 'nightSleepEligible must be a method');
assert(m.isLateNight.call({ hour: 22 }) === false, '22:00 is not late night');
assert(m.isLateNight.call({ hour: 23 }) === true, '23:00 is late night');
assert(m.isLateNight.call({ hour: 5 }) === true, '05:00 is late night');
assert(m.isLateNight.call({ hour: 6 }) === false, '06:00 is not late night');

const pending = {
  hour: 23,
  isLateNight() { return m.isLateNight.call(this); },
  planItems: [{ state: 'scheduled' }],
};
assert(m.nightSleepEligible.call(pending) === false, 'pending item must block night sleep');
const done = { ...pending, planItems: [{ state: 'triggered' }, { state: 'cancelled' }] };
assert(m.nightSleepEligible.call(done) === true, 'terminal items allow night sleep');

const pool = m.randomPool.call({
  keywordAction: () => 'sleep',
  event: 'imminent',
  sleepSuppressedUntil: 0,
  sleepBias: 0,
  nightSleepEligible: () => true,
});
assert(pool.some(([action]) => action === 'sleep'), 'sleep must be in random pool');
assert(pool.some(([action]) => action === 'look'), 'event action must be in random pool');
assert(pool.some(([action]) => action === 'jump'), 'base actions must remain');

const awake = { action: 'sleep', stickyAction: true, stickyUntil: 9999999999999, sleepBias: 0, sleepSuppressedUntil: 0 };
m.wakeFromSleep.call(awake);
assert(awake.action === 'idle', 'interaction must wake sleeping pet');
assert(awake.stickyAction === false, 'wake must clear sticky sleep');
assert(awake.sleepBias === 1, 'interaction must increase later sleep bias');
assert(awake.sleepSuppressedUntil > Date.now(), 'wake must suppress immediate sleep');

const suppressed = m.randomPool.call({
  keywordAction: () => 'sleep',
  event: 'quiet',
  sleepSuppressedUntil: Date.now() + 10000,
  sleepBias: 3,
  nightSleepEligible: () => true,
});
assert(!suppressed.some(([action]) => action === 'sleep'), 'suppressed sleep must not be in pool');

function actionHarness(overrides = {}) {
  return {
    hour: 23,
    action: 'idle',
    dragging: false,
    actionLockUntil: 0,
    stickyAction: false,
    stickyUntil: 0,
    interactionLockUntil: 0,
    event: 'quiet',
    planItems: [],
    sleepBias: 0,
    sleepSuppressedUntil: 0,
    keywordAction: () => '',
    isLateNight() { return m.isLateNight.call(this); },
    nightSleepEligible() { return m.nightSleepEligible.call(this); },
    pickIdle: () => 'idle',
    randomPool: () => [['idle', 1]],
    startJump() { this.action = 'jump'; },
    setAction(action) { this.action = action; },
    speechFor() { return ''; },
    ...overrides,
  };
}

const late = actionHarness();
m.chooseAction.call(late, true);
assert(late.action === 'sleep', '23:00 with no pending items must auto-sleep');

const early = actionHarness({ hour: 22 });
m.chooseAction.call(early, true);
assert(early.action !== 'sleep', '22:00 must not auto-sleep');

const busy = actionHarness({ planItems: [{ state: 'scheduled' }] });
m.chooseAction.call(busy, true);
assert(busy.action !== 'sleep', 'pending item must prevent night sleep');

const scheduledRest = actionHarness({ hour: 19, keywordAction: () => 'sleep' });
m.chooseAction.call(scheduledRest, true);
assert(scheduledRest.action === 'sleep', 'rest schedule must sleep at any hour');

const woken = actionHarness();
m.wakeFromSleep.call(woken);
m.chooseAction.call(woken, true);
assert(woken.action !== 'sleep', 'interaction suppression must prevent immediate re-sleep');

console.log('PET_LOGIC_OK');

