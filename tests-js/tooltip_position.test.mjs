// Unit tests for dlux/static/dlux/helpers/tooltip/js/main.js
//
// Run:  node --test 'tests-js/*.test.mjs'
//
// The tooltip is position:fixed with an auto width, so the browser's shrink-to-fit
// rule caps its width at the space between the applied `left` and the right edge of
// the viewport. positionTooltip() must therefore not measure the box while a previous
// placement's `left` is still on the element: a stale offset (left behind by a resize,
// e.g. docking dev tools) collapses the measurement and walks the tooltip a few pixels
// on every hover. The fake rect below models that rule so the regression is testable.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));

const PREFERRED_WIDTH = 210;
const LINE_HEIGHT = 34;
const MIN_WIDTH = 40;

class ClassList {
  constructor(owner) {
    this.owner = owner;
    this.values = new Set();
  }

  add(...names) {
    names.filter(Boolean).forEach((name) => this.values.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }

  contains(name) {
    return this.values.has(name);
  }
}

class Element {
  constructor(tagName) {
    this.tagName = String(tagName || 'div').toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.classList = new ClassList(this);
    this.style = {
      setProperty(name, value) { this[name] = value; },
    };
    this.textContent = '';
  }

  set className(value) {
    this.attributes.set('class', value);
    this.classList.values = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  get className() {
    return this.attributes.get('class') || '';
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  hasAttribute(name) { return this.attributes.has(name); }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  contains(node) {
    if (node === this) return true;
    return this.children.some((child) => child.contains(node));
  }

  // Only the attribute-presence selectors the tooltip configs use.
  closest(selector) {
    const attribute = selector.replace(/^\[|\]$/g, '');
    let node = this;
    while (node) {
      if (node.hasAttribute && node.hasAttribute(attribute)) return node;
      node = node.parentNode;
    }
    return null;
  }
}

class Document extends Element {
  constructor() {
    super('#document');
    this.eventListeners = {};
    this.body = new Element('body');
    this.body.parentNode = this;
    this.documentElement = new Element('html');
  }

  createElement(tagName) { return new Element(tagName); }

  addEventListener(type, listener) {
    this.eventListeners[type] = this.eventListeners[type] || [];
    this.eventListeners[type].push(listener);
  }

  dispatch(type, event) {
    (this.eventListeners[type] || []).forEach((listener) => listener(event));
  }
}

globalThis.window = globalThis;
globalThis.Element = Element;
globalThis.Node = Element;
globalThis.requestAnimationFrame = (fn) => { fn(); return 0; };
globalThis.cancelAnimationFrame = () => {};
globalThis.addEventListener = () => {};
globalThis.document = new Document();

require(path.join(here, '..', 'dlux', 'static', 'dlux', 'helpers', 'tooltip', 'js', 'main.js'));

globalThis.document.dispatch('DOMContentLoaded', {});

const tooltip = globalThis.document.body.children.find((node) => node.getAttribute('role') === 'tooltip');

// Model the browser: a fixed, auto-width box is bounded by the room to its right, and
// wraps to more lines as it narrows.
tooltip.getBoundingClientRect = function boundingRect() {
  const left = parseFloat(this.style.left) || 0;
  const available = globalThis.window.innerWidth - left;
  const width = Math.max(MIN_WIDTH, Math.min(PREFERRED_WIDTH, available));
  return {
    width,
    height: LINE_HEIGHT * Math.ceil(PREFERRED_WIDTH / width),
    left,
    top: parseFloat(this.style.top) || 0,
  };
};

function makeTarget({ left, width = 36, top = 8, height = 36 }) {
  const button = new Element('button');
  button.setAttribute('data-dlux-tooltip', 'Notifications and alerts centre');
  const icon = new Element('i');
  button.appendChild(icon);
  globalThis.document.body.appendChild(button);
  button.getBoundingClientRect = () => ({
    left, right: left + width, width, top, bottom: top + height, height,
  });
  return { button, icon };
}

function hover(node) {
  globalThis.document.dispatch('pointerover', { target: node });
  return { left: tooltip.style.left, width: tooltip.getBoundingClientRect().width };
}

test('repeated hovers on one target keep the tooltip in the same place', () => {
  globalThis.window.innerWidth = 980;
  globalThis.window.innerHeight = 700;
  const { button, icon } = makeTarget({ left: 936 });

  const first = hover(button);
  // pointerover fires again for every descendant the pointer crosses inside the button.
  const repeats = [hover(icon), hover(button), hover(icon), hover(button)];

  repeats.forEach((result, index) => {
    assert.equal(result.left, first.left, `hover ${index + 1} moved the tooltip`);
    assert.equal(result.width, first.width, `hover ${index + 1} resized the tooltip`);
  });
});

test('a placement left over from a wider viewport does not skew the next hover', () => {
  globalThis.window.innerWidth = 980;
  globalThis.window.innerHeight = 700;
  const { button } = makeTarget({ left: 936 });
  const clean = hover(button);

  // Settle at a wide viewport, then narrow it the way docking dev tools does. The
  // resize handler hides the tooltip but leaves its `left` on the element.
  globalThis.window.innerWidth = 1400;
  hover(button);
  globalThis.window.innerWidth = 980;
  globalThis.document.dispatch('click', {});

  assert.equal(hover(button).left, clean.left);
});
