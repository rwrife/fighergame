export class AnimationPlayer {
  constructor(clips) {
    for (const name of ["idle", "jump", "punch"]) {
      const clip = clips[name];
      if (!clip || !Number.isFinite(clip.fps) || clip.fps <= 0 ||
          !Array.isArray(clip.frames) || !clip.frames.length ||
          clip.loop !== (name === "idle"))
        throw new Error(`Invalid ${name} clip`);
    }
    this.clips = clips;
    this.state = "idle";
    this.elapsed = 0;
    this.queued = null;
    this.history = [];
    this.recovering = false;
  }

  get frame() {
    const clip = this.clips[this.state];
    const index = Math.floor(this.elapsed * clip.fps + 1e-9);
    return clip.loop ? index % clip.frames.length : Math.min(index, clip.frames.length - 1);
  }

  enter(state) {
    this.history.push(`${this.state} -> ${state}`);
    this.history = this.history.slice(-8);
    this.state = state;
    this.elapsed = 0;
  }

  request(state) {
    if (state !== "jump" && state !== "punch") throw new Error(`Unknown move: ${state}`);
    if (this.state === "idle" && !this.recovering) this.enter(state);
    else this.queued = state;
  }

  reset() {
    this.enter("idle");
    this.queued = null;
    this.recovering = false;
  }

  advance(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) throw new Error("Invalid animation time");
    // Consume the entire time step even when it crosses a clip boundary.
    while (seconds > 0) {
      const clip = this.clips[this.state];
      if (this.state === "idle") {
        const bridge = 2 / clip.fps;
        if (this.recovering) {
          const amount = Math.min(seconds, Math.max(0, bridge - this.elapsed));
          this.elapsed += amount;
          seconds -= amount;
          if (this.elapsed + 1e-9 < bridge) break;
          this.recovering = false;
        }
        if (this.queued) {
          const move = this.queued;
          this.queued = null;
          this.enter(move);
          continue;
        }
        this.elapsed = (this.elapsed + seconds) % (clip.frames.length / clip.fps);
        break;
      }
      const remaining = clip.frames.length / clip.fps - this.elapsed;
      const amount = Math.min(seconds, Math.max(0, remaining));
      this.elapsed += amount;
      seconds -= amount;
      if (this.elapsed + 1e-9 < clip.frames.length / clip.fps) break;
      this.enter("idle");
      this.recovering = true;
    }
  }
}
