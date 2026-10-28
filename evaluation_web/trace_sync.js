/* Frame zero is the initial observation. Frame t > 0 is action t-1's ACK. */
(function (root) {
  'use strict';
  function callAtTime(calls, seconds, dt) {
    if (!Number.isFinite(seconds) || !Number.isFinite(dt) || dt <= 0 || seconds < 0) return null;
    const frame = Math.floor(seconds / dt + 1e-6);
    return calls.find(c => c.status === 'executed' && Number.isFinite(c.step_start) && Number.isFinite(c.step_end)
      && c.step_end > c.step_start && frame > c.step_start && frame <= c.step_end) || null;
  }
  function timeForCall(call, dt, phase = 'start') {
    if (!call || !Number.isFinite(dt) || dt <= 0 || !Number.isFinite(call.step_start)) return null;
    if (phase === 'before' || call.status !== 'executed') return call.step_start * dt;
    if (!Number.isFinite(call.step_end) || call.step_end <= call.step_start) return null;
    return (phase === 'after' ? call.step_end : call.step_start + 1) * dt;
  }
  const api = {callAtTime, timeForCall};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EvalTraceSync = api;
})(globalThis);
