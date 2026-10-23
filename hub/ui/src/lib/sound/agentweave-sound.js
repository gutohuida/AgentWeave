/*
 * AgentWeave's sound: the struck glass (S4b, operator's pick in sound round 2, 2026-10-23,
 * https://claude.ai/artifact/RfWBxnGPvLVfGohYbHnPbr).
 *
 * One instrument. Each note is two sine tones that begin slightly apart, beating, and settle into
 * one clean tone (murk becoming clear: "nothing appears out of thin air"), struck by a small hard
 * mallet so it carries across a room. A failure is the one sound that never settles.
 *
 * The opening plays one note per corner of the W as the splash draws it (left to right in the
 * stereo field), then a soft chord as the name appears. Every other sound keeps one shape:
 * needs you rises, done steps down and resolves, stalled is low and falls, ready is a bright pair.
 *
 * This file is the single source. The CLI's launch WAVs are rendered from it offline
 * (scripts/render_opening_sound.py), and the app's notification sounds play it live, so what was
 * approved is what plays. No dependencies; works with any AudioContext or OfflineAudioContext:
 *
 *   const sound = AgentWeaveSound.create(new AudioContext(), { key: 'D', gain: 0.7 });
 *   sound.play('ask');            // 'open' | 'openShort' | 'ask' | 'done' | 'fail' | 'ready'
 */
(function (root) {
  'use strict';

  var ROOT = { C: 261.63, D: 293.66, E: 329.63, G: 392.0, A: 440.0 };
  // When the splash's thread passes each corner of the W (easeOutCubic over 1.3 s), and where.
  var CORNERS = [0, 0.099, 0.268, 0.525, 0.896];
  var PAN = [-0.7, -0.44, 0, 0.29, 0.6];
  var NAME_AT = 1.3;
  var WARM_SPEED = 1.8; // a warm open plays the splash intro 1.8x faster
  // Seconds each sound needs, tail included, for an offline render.
  var LENGTHS = { open: 4.6, openShort: 3.0, ask: 1.8, done: 1.8, fail: 2.0, ready: 1.8 };

  function seeded(seed) {
    return function () {
      seed = (seed * 16807) % 2147483647;
      return (seed / 2147483647) * 2 - 1;
    };
  }

  function create(ctx, options) {
    options = options || {};
    var key = options.key || 'D';
    var start = ctx.currentTime;

    // master -> compressor -> out; a dry bus and a small, always identical room
    var comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -16;
    comp.ratio.value = 3;
    var master = ctx.createGain();
    master.gain.value = options.gain == null ? 0.7 : options.gain;
    master.connect(comp);
    comp.connect(options.destination || ctx.destination);
    var dry = ctx.createGain();
    dry.connect(master);
    var conv = ctx.createConvolver();
    var len = Math.floor(ctx.sampleRate * 2.2);
    var ir = ctx.createBuffer(2, len, ctx.sampleRate);
    var rnd = seeded(17);
    for (var ch = 0; ch < 2; ch++) {
      var x = ir.getChannelData(ch);
      for (var i = 0; i < len; i++) x[i] = rnd() * Math.pow(1 - i / len, 3.4);
    }
    conv.buffer = ir;
    var wet = ctx.createGain();
    wet.gain.value = 0.2;
    wet.connect(conv);
    conv.connect(master);

    var tick = null; // the mallet's noise, made once
    function mallet() {
      if (tick) return tick;
      var n = Math.floor(ctx.sampleRate * 0.05);
      tick = ctx.createBuffer(1, n, ctx.sampleRate);
      var d = tick.getChannelData(0), r = seeded(99);
      for (var k = 0; k < n; k++) d[k] = r();
      return tick;
    }

    function T(at) { return Math.max(ctx.currentTime, start) + 0.03 + at; }
    function hz(s) { return ROOT[key] * Math.pow(2, s / 12); }
    function bus(pan) {
      var g = ctx.createGain(), p = ctx.createStereoPanner();
      p.pan.value = pan || 0;
      g.connect(p);
      p.connect(dry);
      var send = ctx.createGain();
      send.gain.value = 1.2;
      p.connect(send);
      send.connect(wet);
      return g;
    }
    function env(g, at, peak, attack, decay) {
      g.gain.setValueAtTime(0.0001, T(at));
      g.gain.exponentialRampToValueAtTime(peak, T(at) + attack);
      g.gain.exponentialRampToValueAtTime(0.0001, T(at) + attack + decay);
    }
    function sine(f, at, dur) {
      var o = ctx.createOscillator();
      o.type = 'sine';
      o.frequency.value = f;
      o.start(T(at));
      o.stop(T(at) + dur);
      return o;
    }

    // One struck-glass note: semitones above the key's root.
    function glass(s, o) {
      var at = o.at || 0, g = o.g == null ? 0.3 : o.g, dur = o.dur || 0.9, settle = o.settle || 0.16;
      var detune = o.detune || 0.012, resolve = o.resolve !== false, strike = o.strike == null ? 0.5 : o.strike;
      var f = hz(s), out = bus(o.pan);
      [1 + detune, 1].forEach(function (k, idx) {
        var v = sine(f * k, at, dur + 0.2);
        if (resolve) v.frequency.exponentialRampToValueAtTime(f, T(at) + settle);
        else v.frequency.setValueAtTime(f * (idx ? 1 : 1 + detune * 0.6), T(at));
        var vg = ctx.createGain();
        env(vg, at, g * (idx ? 0.6 : 0.5), 0.008, dur);
        v.connect(vg);
        vg.connect(out);
      });
      var oct = sine(f * 2, at, dur), og = ctx.createGain();
      env(og, at, g * 0.12, 0.08, dur * 0.6);
      oct.connect(og);
      og.connect(out);
      if (strike) {
        var n = ctx.createBufferSource();
        n.buffer = mallet();
        var bp = ctx.createBiquadFilter();
        bp.type = 'bandpass';
        bp.frequency.value = Math.min(9000, f * 6);
        bp.Q.value = 3;
        var ng = ctx.createGain();
        env(ng, at, g * strike, 0.001, 0.04);
        n.connect(bp);
        bp.connect(ng);
        ng.connect(out);
        n.start(T(at));
      }
    }

    var sounds = {
      open: function () {
        [0, 7, 12, 14, 19].forEach(function (s, i) {
          glass(s, { at: CORNERS[i], g: i === 2 ? 0.3 : 0.24, pan: PAN[i], dur: 1.6, settle: 0.18 });
        });
        [0, 7, 16].forEach(function (s, i) {
          glass(s, { at: NAME_AT + i * 0.045, g: 0.17, pan: (i - 1) * 0.35, dur: 2.0, settle: 0.25, detune: 0.006, strike: 0.3 });
        });
      },
      openShort: function () {
        [[0, 0], [12, 2], [19, 4]].forEach(function (n) {
          glass(n[0], { at: CORNERS[n[1]] / WARM_SPEED, g: 0.26, pan: PAN[n[1]], dur: 1.4, settle: 0.18 });
        });
      },
      ask: function () {
        glass(7, { g: 0.3, pan: -0.15 });
        glass(14, { at: 0.13, g: 0.315, pan: 0.15 });
      },
      done: function () {
        glass(14, { g: 0.225 });
        glass(12, { at: 0.11, g: 0.255 });
      },
      fail: function () {
        glass(-5, { g: 0.32, dur: 0.9, resolve: false, detune: 0.02, strike: 0.4 });
        glass(-9, { at: 0.2, g: 0.32, dur: 1.1, resolve: false, detune: 0.02, strike: 0.4 });
      },
      ready: function () {
        glass(12, { g: 0.21, pan: -0.2 });
        glass(19, { at: 0.03, g: 0.18, pan: 0.2 });
      },
    };

    return {
      master: master,
      play: function (name) {
        if (!sounds[name]) throw new Error('AgentWeave has no sound named ' + name);
        sounds[name]();
      },
      setKey: function (k) { if (ROOT[k]) key = k; },
    };
  }

  // Render one sound offline to a 16-bit stereo WAV (bytes), peak at -6 dBFS.
  function renderWav(name, options) {
    options = options || {};
    var rate = options.sampleRate || 44100;
    var Offline = root.OfflineAudioContext || root.webkitOfflineAudioContext;
    var off = new Offline(2, Math.ceil(rate * LENGTHS[name]), rate);
    create(off, { key: options.key, gain: 0.9 }).play(name);
    return off.startRendering().then(function (buf) {
      var L = buf.getChannelData(0), R = buf.getChannelData(1), n = buf.length, peak = 0;
      for (var i = 0; i < n; i++) peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
      var scale = peak > 0 ? 0.5 / peak : 1;
      var view = new DataView(new ArrayBuffer(44 + n * 4));
      function str(o, s) { for (var c = 0; c < s.length; c++) view.setUint8(o + c, s.charCodeAt(c)); }
      str(0, 'RIFF'); view.setUint32(4, 36 + n * 4, true); str(8, 'WAVEfmt ');
      view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 2, true);
      view.setUint32(24, rate, true); view.setUint32(28, rate * 4, true); view.setUint16(32, 4, true);
      view.setUint16(34, 16, true); str(36, 'data'); view.setUint32(40, n * 4, true);
      for (var j = 0, o = 44; j < n; j++, o += 4) {
        view.setInt16(o, Math.round(Math.max(-1, Math.min(1, L[j] * scale)) * 32767), true);
        view.setInt16(o + 2, Math.round(Math.max(-1, Math.min(1, R[j] * scale)) * 32767), true);
      }
      return new Uint8Array(view.buffer);
    });
  }

  var api = { create: create, renderWav: renderWav, LENGTHS: LENGTHS };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.AgentWeaveSound = api;
})(typeof window !== 'undefined' ? window : globalThis);
