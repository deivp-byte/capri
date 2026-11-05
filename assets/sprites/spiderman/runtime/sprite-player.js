/*
 * SpiderSpritePlayer — lightweight canvas renderer for this sprite pack.
 * No network service, framework or AI model is required.
 * Browser: <script src="runtime/sprite-player.js"></script>
 * Node: const { SpiderSpritePlayer } = require('./sprite-player.js');
 */
(function (root) {
  'use strict';

  class SpiderSpritePlayer {
    constructor(manifest, options = {}) {
      if (!manifest || !manifest.animations || !manifest.sheets) {
        throw new TypeError('A sprite manifest with animations and sheets is required.');
      }
      this.manifest = manifest;
      this.baseUrl = options.baseUrl || '';
      this.imageSources = options.imageSources || {};
      this.images = options.images || {};
      this.speed = 1;
      this.flipX = false;
      this.elapsedMs = 0;
      this.finished = false;
      this.onComplete = options.onComplete || null;
      this.animationName = null;
      this.animationId = null;
      this.animation = null;
      this.reverse = false;
      this.loopOverride = null;
      this._completionSent = false;
      const initial = options.animation || Object.keys(manifest.animations)[0];
      if (initial) this.setAnimation(initial);
    }

    async load() {
      await Promise.all(Object.entries(this.manifest.sheets).map(async ([id, sheet]) => {
        if (this.images[id]) return;
        const source = this.imageSources[id] || this.resolveUrl(sheet.file);
        this.images[id] = await SpiderSpritePlayer.loadImage(source);
      }));
      return this;
    }

    resolveUrl(path) {
      if (/^(data:|blob:|https?:|file:)/.test(path)) return path;
      return this.baseUrl + path;
    }

    static loadImage(source) {
      return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = () => reject(new Error('Cannot load sprite sheet: ' + source.slice(0, 120)));
        image.src = source;
      });
    }

    resolveAnimation(name) {
      let id = name;
      let flipX = false;
      let reverse = false;
      let depth = 0;
      while (!this.manifest.animations[id] && this.manifest.aliases?.[id]) {
        if (++depth > 12) throw new Error('Circular animation alias: ' + name);
        const alias = this.manifest.aliases[id];
        if (typeof alias === 'string') {
          id = alias;
        } else {
          flipX = flipX !== Boolean(alias.flipX);
          reverse = reverse !== Boolean(alias.reverse);
          id = alias.animation || alias.source;
        }
      }
      const animation = this.manifest.animations[id];
      if (!animation) throw new Error('Unknown animation: ' + name);
      if (!Array.isArray(animation.frames) || !animation.frames.length) {
        throw new Error('Animation has no frames: ' + id);
      }
      return { id, animation, flipX, reverse };
    }

    setAnimation(name, options = {}) {
      const result = this.resolveAnimation(name);
      const same = name === this.animationName;
      if (same && options.restart === false) {
        if (typeof options.flipX === 'boolean') this.flipX = options.flipX;
        if (options.loop !== undefined) this.loopOverride = options.loop;
        return this;
      }
      this.animationName = name;
      this.animationId = result.id;
      this.animation = result.animation;
      this.reverse = options.reverse ?? result.reverse;
      this.flipX = options.flipX ?? result.flipX;
      this.loopOverride = options.loop ?? null;
      this.elapsedMs = 0;
      this.finished = false;
      this._completionSent = false;
      return this;
    }

    setDirection(direction) {
      this.flipX = direction === 'left' || direction === -1 || direction === true;
      return this;
    }

    setSpeed(speed) {
      if (!Number.isFinite(speed) || speed < 0) throw new RangeError('Speed must be a finite nonnegative number.');
      this.speed = speed;
      return this;
    }

    getFrameDuration(frame, originalIndex) {
      return Math.max(1, frame.durationMs ?? this.animation.frameDurationsMs?.[originalIndex] ?? (1000 / (this.animation.fps || 8)));
    }

    get durationMs() {
      return this.animation.frames.reduce((sum, frame, i) => sum + this.getFrameDuration(frame, i), 0);
    }

    get loop() {
      return this.loopOverride === null ? Boolean(this.animation.loop) : Boolean(this.loopOverride);
    }

    update(deltaSeconds) {
      if (!Number.isFinite(deltaSeconds) || deltaSeconds < 0) throw new RangeError('deltaSeconds must be finite and nonnegative.');
      if (this.finished && !this.loop) return this;
      const duration = this.durationMs;
      this.elapsedMs += deltaSeconds * 1000 * this.speed;
      if (this.loop) {
        this.elapsedMs %= duration;
        this.finished = false;
      } else if (this.elapsedMs >= duration) {
        this.elapsedMs = duration;
        this.finished = true;
        if (!this._completionSent) {
          this._completionSent = true;
          if (this.onComplete) this.onComplete(this.animationName, this.animation.next ?? null, this);
        }
      }
      return this;
    }

    seek(milliseconds) {
      if (!Number.isFinite(milliseconds)) throw new RangeError('Time must be finite.');
      this.elapsedMs = Math.min(this.durationMs, Math.max(0, milliseconds));
      this.finished = !this.loop && this.elapsedMs >= this.durationMs;
      this._completionSent = false;
      return this;
    }

    get current() {
      const frames = this.animation.frames;
      let time = this.elapsedMs;
      const order = frames.map((_, i) => i);
      if (this.reverse) order.reverse();
      for (let position = 0; position < order.length; position++) {
        const index = order[position];
        const frame = frames[index];
        const duration = this.getFrameDuration(frame, index);
        if (time < duration || position === order.length - 1) {
          return { frame, index, position, durationMs: duration, pivot: this.getPivot(frame) };
        }
        time -= duration;
      }
      return null;
    }

    getPivot(frame) {
      const fallback = this.manifest.defaultPivot || {
        x: (frame.w ?? frame.width ?? this.manifest.frameSize?.width ?? 128) / 2,
        y: (frame.h ?? frame.height ?? this.manifest.frameSize?.height ?? 128) - 12
      };
      return frame.pivot || this.animation.pivot || fallback;
    }

    draw(context, x, y, options = {}) {
      const current = this.current;
      if (!current) return;
      const frame = current.frame;
      const image = this.images[frame.sheet || this.animation.sheet];
      if (!image) return;
      const width = frame.w ?? frame.width ?? this.manifest.frameSize?.width ?? 128;
      const height = frame.h ?? frame.height ?? this.manifest.frameSize?.height ?? 128;
      const pivot = options.pivot || current.pivot;
      const scale = options.scale ?? 1;
      const flipX = options.flipX ?? this.flipX;
      context.save();
      context.imageSmoothingEnabled = false;
      context.globalAlpha *= options.alpha ?? 1;
      context.translate(Math.round(x), Math.round(y));
      context.scale(flipX ? -scale : scale, scale);
      context.drawImage(image, frame.x, frame.y, width, height, -pivot.x, -pivot.y, width, height);
      context.restore();
    }

    /** Local point -> canvas point, useful for attaching a separately rendered web. */
    localToWorld(point, x, y, scale = 1) {
      const pivot = this.current.pivot;
      return {
        x: x + (point.x - pivot.x) * scale * (this.flipX ? -1 : 1),
        y: y + (point.y - pivot.y) * scale
      };
    }
  }

  if (typeof module === 'object' && module.exports) module.exports = { SpiderSpritePlayer };
  if (root) root.SpiderSpritePlayer = SpiderSpritePlayer;
})(typeof window !== 'undefined' ? window : globalThis);
