'use strict';
const assert = require('node:assert/strict');
const {callAtTime, timeForCall} = require('../evaluation_web/trace_sync.js');
const a = {id:'first', status:'executed', step_start:0, step_end:3};
const rejected = {id:'rejected', status:'rejected', step_start:3, step_end:3};
const b = {id:'second', status:'executed', step_start:3, step_end:8};
const unknown = {id:'unknown', status:'uncertain', step_start:8, step_end:10};
const calls = [a,rejected,b,unknown];
assert.equal(callAtTime(calls,0,0.04),null); // Initial frame has no action.
assert.equal(callAtTime(calls,0.04,0.04),a);
assert.equal(callAtTime(calls,0.12,0.04),a); // End ACK belongs to the first action.
assert.equal(callAtTime(calls,0.159,0.04),a);
assert.equal(callAtTime(calls,0.16,0.04),b); // Second action's first ACK.
assert.equal(callAtTime(calls,0.32,0.04),b);
assert.equal(callAtTime(calls,0.36,0.04),null); // Uncertain execution is not attributed.
assert.equal(callAtTime(calls,-1,0.04),null);
assert.equal(callAtTime(calls,1,0),null);
assert.equal(callAtTime(calls,NaN,0.04),null);
assert.equal(timeForCall(a,0.04),0.04);
assert.equal(timeForCall(a,0.04,'before'),0);
assert.equal(timeForCall(a,0.04,'after'),0.12);
assert.equal(timeForCall(b,0.04),0.16);
assert.equal(timeForCall(rejected,0.04),0.12);
assert.equal(timeForCall(null,0.04),null);
assert.equal(timeForCall(a,0),null);
console.log('17 frame/call alignment assertions passed');
