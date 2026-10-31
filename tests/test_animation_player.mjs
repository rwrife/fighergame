import assert from "node:assert/strict";
import { test } from "node:test";
import { AnimationPlayer } from "../demos/animation_player.mjs";

const clips = {
  idle: { fps: 8, loop: true, frames: Array(27).fill({}) },
  jump: { fps: 8, loop: false, frames: Array(16).fill({}) },
  punch: { fps: 8, loop: false, frames: Array(9).fill({}) },
};

test("idle loops without changing state", () => {
  const player = new AnimationPlayer(clips);
  player.advance(27 / 8 + 5 / 8);
  assert.equal(player.state, "idle");
  assert.equal(player.frame, 5);
});

test("jump and punch show their final frames, then recover to idle", () => {
  for (const name of ["jump", "punch"]) {
    const player = new AnimationPlayer(clips);
    player.request(name);
    player.advance((clips[name].frames.length - 1) / 8);
    assert.equal(player.state, name);
    assert.equal(player.frame, clips[name].frames.length - 1);
    player.advance(1 / 8);
    assert.equal(player.state, "idle");
    assert.equal(player.frame, 0);
  }
});

test("queued actions finish the current move and cross two idle frames", () => {
  const player = new AnimationPlayer(clips);
  player.request("jump");
  player.request("punch");
  player.advance(2);
  assert.equal(player.state, "idle");
  assert.equal(player.queued, "punch");
  player.advance(1 / 8);
  assert.equal(player.state, "idle");
  player.advance(1 / 8 + .001);
  assert.equal(player.state, "punch");
  assert.equal(player.queued, null);
  assert.deepEqual(player.history, ["idle -> jump", "jump -> idle", "idle -> punch"]);
});

test("newest queued move wins and reset cancels the queue", () => {
  const player = new AnimationPlayer(clips);
  player.request("punch");
  player.request("punch");
  player.request("jump");
  assert.equal(player.queued, "jump");
  player.reset();
  assert.equal(player.state, "idle");
  assert.equal(player.queued, null);
  player.advance(20);
  assert.equal(player.state, "idle");
});

test("large time steps carry across action and recovery boundaries", () => {
  const player = new AnimationPlayer(clips);
  player.request("jump");
  player.request("punch");
  player.advance(2 + 2 / 8 + 9 / 8 + 3 / 8);
  assert.equal(player.state, "idle");
  assert.equal(player.frame, 3);
  assert.equal(player.queued, null);
});

test("reject invalid time, states, and metadata", () => {
  const player = new AnimationPlayer(clips);
  assert.throws(() => player.request("kick"));
  for (const seconds of [-1, NaN, Infinity]) assert.throws(() => player.advance(seconds));
  assert.throws(() => new AnimationPlayer({ ...clips, jump: { ...clips.jump, loop: true } }));
});
