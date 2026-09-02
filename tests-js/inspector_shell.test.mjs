// Unit tests for dlux/static/dlux/helpers/inspector/js/main.js
//
// Run:  node --test 'tests-js/*.test.mjs'
//
// The inspector shell is intentionally adapter-driven. These tests exercise the
// behavior that matters before migrating builders: render does not commit, field
// events commit exactly once, Clear is appended/pinned, and localized fields
// report the edited language to the adapter.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));

function dataKey(attribute) {
  return attribute.replace(/^data-/, '').replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

class ClassList {
  constructor(owner) {
    this.owner = owner;
    this.values = new Set();
  }

  add(...names) {
    names.filter(Boolean).forEach((name) => this.values.add(name));
    this.sync();
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
    this.sync();
  }

  contains(name) {
    return this.values.has(name);
  }

  toggle(name, force) {
    const next = force === undefined ? !this.values.has(name) : Boolean(force);
    if (next) this.values.add(name);
    else this.values.delete(name);
    this.sync();
    return next;
  }

  setFromString(value) {
    this.values = new Set(String(value || '').split(/\s+/).filter(Boolean));
  }

  sync() {
    this.owner._className = Array.from(this.values).join(' ');
  }

  get length() {
    return this.values.size;
  }

  toString() {
    return Array.from(this.values).join(' ');
  }
}

class TestEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.bubbles = Boolean(options.bubbles);
    this.detail = options.detail || null;
    this.target = null;
  }
}

class Element {
  constructor(tagName) {
    this.tagName = String(tagName || '').toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.dataset = {};
    this.eventListeners = {};
    this.hidden = false;
    this.parentNode = null;
    this.textContent = '';
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.classList = new ClassList(this);
    this._className = '';
    this.style = {};
    this.offsetHeight = 0;
    this.scrollHeight = 0;
    this.clientHeight = 0;
    this.nodeType = 1;
  }

  // The shell walks siblings to find out-of-flow layers without descending into them.
  get firstElementChild() {
    return this.children[0] || null;
  }

  get nextElementSibling() {
    if (!this.parentNode) return null;
    const at = this.parentNode.children.indexOf(this);
    return at === -1 ? null : (this.parentNode.children[at + 1] || null);
  }

  // Zero-sized unless a test gives the element a rect of its own.
  getBoundingClientRect() {
    return { top: 0, bottom: 0, left: 0, right: 0, height: 0, width: 0 };
  }

  set className(value) {
    this._className = String(value || '');
    this.classList.setFromString(this._className);
  }

  get className() {
    return this._className;
  }

  set innerHTML(value) {
    this.children = [];
    this._innerHTML = String(value || '');
  }

  get innerHTML() {
    return this._innerHTML || '';
  }

  appendChild(child) {
    this.removeChild(child);
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  removeChild(child) {
    const at = this.children.indexOf(child);
    if (at !== -1) this.children.splice(at, 1);
    return child;
  }

  insertBefore(child, reference) {
    this.removeChild(child);
    child.parentNode = this;
    const at = this.children.indexOf(reference);
    if (at === -1) this.children.push(child);
    else this.children.splice(at, 0, child);
    return child;
  }

  // The shell walks `parentElement` looking for whatever clips it, and reads
  // `ownerDocument.defaultView` to get at getComputedStyle.
  get parentElement() {
    return this.parentNode && this.parentNode.tagName !== 'BODY' ? this.parentNode : null;
  }

  get ownerDocument() {
    return globalThis.document;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === 'class') this.className = value;
  }

  getAttribute(name) {
    return this.attributes.get(name) || null;
  }

  addEventListener(type, listener) {
    this.eventListeners[type] = this.eventListeners[type] || [];
    this.eventListeners[type].push(listener);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    (this.eventListeners[event.type] || []).forEach((listener) => listener(event));
    if (event.bubbles && this.parentNode) this.parentNode.dispatchEvent(event);
    return true;
  }

  click() {
    this.dispatchEvent(new TestEvent('click', { bubbles: true }));
  }

  matches(selector) {
    if (selector.startsWith('.')) {
      return this.classList.contains(selector.slice(1));
    }
    if (selector.startsWith('[') && selector.endsWith(']')) {
      const body = selector.slice(1, -1);
      const [rawName, rawValue] = body.split('=');
      const name = rawName.trim();
      const expected = rawValue ? rawValue.trim().replace(/^["']|["']$/g, '') : null;
      const actual = name.startsWith('data-') ? this.dataset[dataKey(name)] : this.getAttribute(name);
      if (expected === null) return actual !== undefined && actual !== null;
      return String(actual || '') === expected;
    }
    return this.tagName.toLowerCase() === selector.toLowerCase();
  }

  contains(node) {
    if (node === this) return true;
    return this.children.some((child) => child.contains(node));
  }

  closest(selector) {
    let node = this;
    while (node) {
      if (node.matches && node.matches(selector)) return node;
      node = node.parentNode;
    }
    return null;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const found = [];
    const visit = (node) => {
      node.children.forEach((child) => {
        if (child.matches(selector)) found.push(child);
        visit(child);
      });
    };
    visit(this);
    return found;
  }
}

class Document {
  constructor() {
    this.documentElement = new Element('html');
    this.body = new Element('body');
    this.documentElement.appendChild(this.body);
    this.eventListeners = {};
    this.defaultView = globalThis;
  }

  createElement(tagName) {
    return new Element(tagName);
  }

  addEventListener(type, listener) {
    this.eventListeners[type] = this.eventListeners[type] || [];
    this.eventListeners[type].push(listener);
  }

  removeEventListener(type, listener) {
    this.eventListeners[type] = (this.eventListeners[type] || []).filter((entry) => entry !== listener);
  }

  querySelector(selector) {
    return this.documentElement.querySelector(selector);
  }
}

globalThis.window = globalThis;
// The shell binds resize/scroll on the window; tests fire them by hand.
globalThis.eventListeners = {};
globalThis.addEventListener = (type, listener) => {
  globalThis.eventListeners[type] = globalThis.eventListeners[type] || [];
  globalThis.eventListeners[type].push(listener);
};
globalThis.removeEventListener = (type, listener) => {
  globalThis.eventListeners[type] = (globalThis.eventListeners[type] || []).filter((e) => e !== listener);
};
globalThis.requestAnimationFrame = (fn) => fn();
// Every element is `visible` unless a test gives it an overflow, which is what
// makes an element a clipping ancestor as far as the shell is concerned.
globalThis.getComputedStyle = (node) => {
  const style = (node && node.style) || {};
  return {
    overflowY: style.overflowY || 'visible',
    position: style.position || 'static',
    display: style.display || 'block',
    visibility: style.visibility || 'visible',
  };
};
globalThis.Node = Element;
globalThis.CustomEvent = TestEvent;
globalThis.document = new Document();

require(path.join(here, '..', 'dlux', 'static', 'dlux', 'helpers', 'inspector', 'js', 'main.js'));

const Shell = globalThis.DluxInspectorShell;

function container() {
  return document.createElement('div');
}

test('namespace exposes the inspector shell factory', () => {
  assert.equal(typeof Shell.create, 'function');
  assert.equal(typeof Shell.createInspectorShell, 'function');
  assert.ok(Shell.fieldTypes.includes('localized-text'));
  assert.ok(Shell.fieldTypes.includes('custom'));
});

test('rendering a selection does not commit or dispatch change', () => {
  const root = container();
  let commits = 0;
  let changes = 0;
  root.addEventListener('dlux:inspector:change', () => {
    changes += 1;
  });
  const shell = Shell.create(root, {
    adapter: {
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
      commit: () => {
        commits += 1;
      },
    },
    includeClearAction: false,
  });

  shell.render({ id: 'node-1' });

  assert.equal(commits, 0);
  assert.equal(changes, 0);
  assert.equal(root.hidden, false);
  assert.equal(root.querySelectorAll('input').length, 1);
});

test('empty-state actions render without forcing the empty panel visible', () => {
  const root = container();
  const shell = Shell.create(root, {
    adapter: {
      getActions: ({ selection }) => selection ? [] : [{ id: 'add-group', label: 'Add Group' }],
    },
  });

  shell.render(null);

  const buttons = root.querySelectorAll('button');
  assert.equal(root.hidden, false);
  assert.equal(buttons.length, 1);
  assert.equal(buttons[0].dataset.inspectorAction, 'add-group');
  assert.equal(root.querySelector('.dlux-inspector-shell__empty').hidden, true);
});

test('an always-available action does not leave an empty editor panel behind', () => {
  // The panel carries a selection's header and fields and nothing else. Tying its
  // visibility to the action count left a bordered but empty card sitting under
  // Nav Bar's always-available Add Group, both before a first selection and after
  // Clear selection.
  const root = container();
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [{ id: 'add-group', label: 'Add Group' }],
      getFields: ({ selection }) => (selection ? [{ id: 'name', type: 'text', value: 'Reports' }] : []),
    },
  });

  const panel = root.querySelector('.dlux-inspector-shell__panel');

  shell.render(null);
  assert.equal(panel.hidden, true);
  assert.equal(root.querySelectorAll('button').length, 1);

  shell.render({ id: 'node-1' });
  assert.equal(panel.hidden, false);

  root.querySelector('[data-inspector-action="clear-selection"]').click();
  assert.equal(panel.hidden, true);
  assert.equal(root.querySelectorAll('button').length, 1);
});

test('popover presentation keeps actions inline and floats the editor panel', () => {
  const root = container();
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [{ id: 'add-group', label: 'Add Group' }],
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
    },
    presentation: 'popover',
  });

  shell.render({ id: 'node-1' });

  const actions = root.querySelector('.dlux-inspector-shell__actions');
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  assert.equal(root.classList.contains('dlux-inspector-shell--popover'), true);
  assert.equal(actions.parentNode, root);
  assert.equal(panel.parentNode, root);
  assert.equal(panel.querySelectorAll('button').length, 0);
  assert.equal(actions.querySelectorAll('button').length, 2);
});

test('a popover anchors below the row it edits, and above it when space runs out', () => {
  const root = container();
  // A stand-in for the selected row: 40px tall, sitting 500px down a 600px view.
  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: 500, bottom: 540, left: 0, right: 100 });
  root.getBoundingClientRect = () => ({ top: 100, bottom: 140, left: 0, right: 100 });

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');

  // 60px of panel, 60px of room below the anchor: it goes below, clear of the row.
  panel.offsetHeight = 60;
  globalThis.window.innerHeight = 700;
  shell.render({ id: 'node-1' });
  assert.equal(panel.dataset.inspectorPlacement, 'below');
  assert.equal(panel.style.top, `${540 - 100 + 8}px`);

  // Same anchor in a 560px view: nothing fits below, so it flips above and still
  // stops short of the row.
  globalThis.window.innerHeight = 560;
  shell.reposition();
  assert.equal(panel.dataset.inspectorPlacement, 'above');
  assert.equal(panel.style.top, `${500 - 100 - 60 - 8}px`);
});

test('a popover measures the box that clips it, not the viewport', () => {
  // The regression: a scrollable modal body 738px down a 1000px viewport. There is
  // 271px of *screen* below the anchor but only 9px inside the modal, so measuring
  // the viewport put the panel past the modal's edge, where it was clipped away and
  // grew the modal's scroll area instead.
  const scroller = new Element('div');
  scroller.style.overflowY = 'auto';
  scroller.getBoundingClientRect = () => ({ top: 30, bottom: 738 });
  globalThis.document.body.appendChild(scroller);

  const root = container();
  scroller.appendChild(root);
  root.getBoundingClientRect = () => ({ top: 100, bottom: 140 });

  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: 689, bottom: 729 });
  scroller.appendChild(anchor);

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  panel.offsetHeight = 145;
  panel.scrollHeight = 145;
  globalThis.window.innerHeight = 1000;

  shell.render({ id: 'node-1' });

  assert.equal(panel.dataset.inspectorPlacement, 'above', 'only 9px fit below inside the modal body');
  // Above the anchor, clear of it, and inside the scroller.
  assert.equal(panel.style.top, `${689 - 145 - 8 - 100}px`);
  assert.ok(!panel.style.maxHeight, 'the panel is never given a height cap');
});

test('a popover too tall for either side stays whole and inside the visible band', () => {
  // It is not capped: a capped panel scrolls, and a scrolling panel clips the layers
  // its fields open over it. It takes the roomier side and is nudged into view.
  const scroller = new Element('div');
  scroller.style.overflowY = 'auto';
  scroller.getBoundingClientRect = () => ({ top: 100, bottom: 300 });
  globalThis.document.body.appendChild(scroller);

  const root = container();
  scroller.appendChild(root);
  root.getBoundingClientRect = () => ({ top: 100, bottom: 130 });

  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: 178, bottom: 232 });
  scroller.appendChild(anchor);

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  panel.offsetHeight = 145;
  globalThis.window.innerHeight = 1000;

  shell.render({ id: 'node-1' });

  assert.ok(!panel.style.maxHeight, 'never capped');
  assert.equal(panel.classList.contains('is-capped'), false);
  const top = Number(String(panel.style.top).replace('px', '')) + 100;
  assert.ok(top >= 100, `panel top ${top} must not escape the scroller`);
  assert.ok(top + 145 <= 300, `panel bottom ${top + 145} must not escape the scroller`);
});

test('actions can live inside the panel, above the fields', () => {
  // For a host with no builder-level toolbar: the actions belong to the entry, so
  // they travel with its panel rather than sitting inline in the host.
  const root = container();
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [{ id: 'remove', label: 'Remove' }],
      getFields: () => [{ id: 'name', type: 'text', value: 'Sent' }],
    },
    actionsPlacement: 'panel',
  });
  shell.render({ id: 'tab-1' });

  const panel = root.querySelector('.dlux-inspector-shell__panel');
  const actions = root.querySelector('.dlux-inspector-shell__actions');
  const fields = root.querySelector('.dlux-inspector-shell__fields');
  assert.equal(actions.parentNode, panel, 'actions belong to the panel');
  assert.ok(panel.children.indexOf(actions) < panel.children.indexOf(fields), 'above the fields');
  assert.equal(root.children.includes(actions), false, 'and not inline in the host');
});

test('a panel carrying only actions still shows', () => {
  // A ribbon strip has no label or icon of its own — its panel is the action row.
  const root = container();
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [{ id: 'remove', label: 'Remove' }],
      getFields: () => [],
      getTitle: () => '',
    },
    actionsPlacement: 'panel',
  });
  shell.render({ id: 'strip-1' });

  const panel = root.querySelector('.dlux-inspector-shell__panel');
  assert.equal(panel.hidden, false, 'nothing but actions is still something to show');
  assert.equal(root.querySelector('.dlux-inspector-shell__fields').hidden, true);
});

test('a toggle action renders as a switch and reports its new value', () => {
  const root = container();
  let received = null;
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [{
        id: 'shown',
        type: 'toggle',
        label: 'Shown',
        checked: true,
        onChange: ({ value }) => {
          received = value;
        },
      }],
      getFields: () => [],
    },
  });
  shell.render({ id: 'tab-1' });

  const wrap = root.querySelector('[data-inspector-action="shown"]');
  assert.ok(wrap.classList.contains('form-switch'), 'a switch, not a button');
  const input = wrap.querySelector('.form-check-input');
  assert.equal(input.checked, true);

  input.checked = false;
  input.dispatchEvent(new TestEvent('change'));
  assert.equal(received, false, 'the callback gets the value the switch now holds');
});

test('a field that opens a floating layer does not resize or move the panel', () => {
  // An icon picker's dropdown is absolutely positioned but still counts toward the
  // panel's scrollable overflow. Measuring scrollHeight read the panel as several
  // times its real height, so the shell capped it and re-anchored around a layer
  // that is not in flow — and every scroll inside that layer did it again.
  const scroller = new Element('div');
  scroller.style.overflowY = 'auto';
  scroller.getBoundingClientRect = () => ({ top: 0, bottom: 900 });
  globalThis.document.body.appendChild(scroller);

  const root = container();
  scroller.appendChild(root);
  root.getBoundingClientRect = () => ({ top: 100, bottom: 140 });
  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: 200, bottom: 240 });
  scroller.appendChild(anchor);

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'name', type: 'text', value: 'Sent' }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  globalThis.window.innerHeight = 900;
  panel.offsetHeight = 200;
  panel.scrollHeight = 200;
  shell.render({ id: 'tab-1' });
  const settled = panel.style.top;
  assert.ok(!panel.style.maxHeight);

  // The dropdown opens: overflow balloons, the panel's own box does not.
  panel.scrollHeight = 530;
  shell.reposition();
  assert.equal(panel.style.top, settled, 'the panel must not move');
  assert.ok(!panel.style.maxHeight, 'and must not cap itself around a floating layer');
});

test('a field layer floats free of the panel: not measured into placement, not capped', () => {
  // The panel is a popover; an icon picker's dropdown opened inside it is another.
  // Measuring the layer into the panel's height made the panel cap itself, and a
  // capped panel scrolls — which clipped the very dropdown to a sliver.
  const scroller = new Element('div');
  scroller.style.overflowY = 'auto';
  scroller.getBoundingClientRect = () => ({ top: 32, bottom: 344 });
  globalThis.document.body.appendChild(scroller);

  const root = container();
  scroller.appendChild(root);
  root.getBoundingClientRect = () => ({ top: 100, bottom: 140 });
  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: 240, bottom: 280 });
  scroller.appendChild(anchor);

  const layer = new Element('div');
  layer.style.position = 'absolute';
  layer.getBoundingClientRect = () => ({ top: 83, bottom: 428, height: 345 });

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'icon', type: 'custom', render: () => layer }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  panel.offsetHeight = 200;
  globalThis.window.innerHeight = 1000;
  shell.render({ id: 'tab-1' });

  // 200px of panel fits above the anchor (208px of room), so it goes above and is
  // not capped — the 345px layer hanging out of it changes none of that.
  assert.equal(panel.dataset.inspectorPlacement, 'above');
  assert.ok(!panel.style.maxHeight, 'a capped panel scrolls, which would clip the layer');
  assert.ok(!layer.style.maxHeight, 'and the layer is left at its own size');
});

test('a scroll inside the panel is ignored; one outside still repositions', () => {
  const root = container();
  root.getBoundingClientRect = () => ({ top: 100, bottom: 140 });
  let anchorTop = 200;
  const anchor = new Element('button');
  anchor.getBoundingClientRect = () => ({ top: anchorTop, bottom: anchorTop + 40 });
  globalThis.document.body.appendChild(anchor);

  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getAnchor: () => anchor,
      getFields: () => [{ id: 'name', type: 'text', value: 'Sent' }],
    },
    presentation: 'popover',
  });
  const panel = root.querySelector('.dlux-inspector-shell__panel');
  globalThis.window.innerHeight = 900;
  panel.offsetHeight = 100;
  shell.render({ id: 'tab-1' });
  const before = panel.style.top;

  const fire = (target) => {
    (globalThis.eventListeners.scroll || []).forEach((handler) => handler({ type: 'scroll', target }));
  };

  // The anchor moves, but the scroll came from inside the panel: no reposition.
  anchorTop = 400;
  fire(panel.querySelector('.dlux-inspector-shell__fields'));
  assert.equal(panel.style.top, before, 'a scroll inside the panel cannot have moved the anchor');

  // The same move, reported by a scroll outside it, is followed.
  fire(anchor);
  assert.equal(panel.style.top, `${400 + 40 + 8 - 100}px`);
});

test('an outside click dismisses the popover, but a click that reselects does not', () => {
  const root = container();
  let clears = 0;
  const shell = Shell.create(root, {
    adapter: {
      getActions: () => [],
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
      clearSelection: () => {
        clears += 1;
      },
    },
    presentation: 'popover',
    dismissOnOutsideClick: true,
    dismissIgnoreSelector: '.row-surface',
  });
  shell.render({ id: 'node-1' });

  const fire = (target) => {
    const handlers = globalThis.document.eventListeners.click || [];
    handlers.forEach((handler) => handler({ target }));
  };

  // A click on another selectable row re-anchors; the host's own handler selects.
  const otherRow = new Element('button');
  otherRow.className = 'row-surface';
  fire(otherRow);
  assert.equal(clears, 0);

  // A click inside the shell is not "outside".
  fire(root.querySelector('.dlux-inspector-shell__fields'));
  assert.equal(clears, 0);

  // Anything else dismisses.
  fire(new Element('div'));
  assert.equal(clears, 1);
  assert.equal(root.querySelector('.dlux-inspector-shell__panel').hidden, true);
});

test('field changes commit once even when a callback also returns commit', () => {
  const root = container();
  let commits = 0;
  const shell = Shell.create(root, {
    adapter: {
      getFields: () => [{
        id: 'label',
        type: 'text',
        value: 'Users',
        onChange: () => ({ commit: true }),
      }],
      commit: () => {
        commits += 1;
      },
    },
    includeClearAction: false,
  });
  shell.render({ id: 'node-1' });

  const input = root.querySelector('input');
  input.value = 'People';
  input.dispatchEvent(new TestEvent('change', { bubbles: true }));

  assert.equal(commits, 1);
});

test('clear selection is appended to the action row and pinned to the end', () => {
  const root = container();
  let clears = 0;
  const shell = Shell.create(root, {
    adapter: {
      getActions: ({ selection }) => selection
        ? [
            { id: 'add', label: 'Add' },
            { id: 'remove', label: 'Remove', variant: 'outline-danger' },
          ]
        : [],
      getFields: () => [{ id: 'name', type: 'text', value: 'Reports' }],
      clearSelection: () => {
        clears += 1;
      },
    },
  });
  shell.render({ id: 'node-1' });

  const buttons = root.querySelectorAll('button');
  assert.deepEqual(buttons.map((button) => button.dataset.inspectorAction), ['add', 'remove', 'clear-selection']);
  assert.equal(buttons[2].classList.contains('dlux-inspector-shell__action--end'), true);

  buttons[2].click();

  assert.equal(clears, 1);
  assert.equal(root.hidden, true);
  assert.equal(root.querySelectorAll('button').length, 0);
});

test('localized text fields pass the edited language into the field callback', () => {
  const root = container();
  const seen = [];
  let commits = 0;
  const shell = Shell.create(root, {
    adapter: {
      getFields: () => [{
        id: 'labels',
        type: 'localized-text',
        languages: [['en', { name: 'English' }], ['ar', { name: 'Arabic' }]],
        values: { en: 'Reports', ar: '' },
        commitOn: 'input',
        onInput: (context) => {
          seen.push([context.language, context.value]);
        },
      }],
      commit: () => {
        commits += 1;
      },
    },
    includeClearAction: false,
  });
  shell.render({ id: 'node-1' });

  const inputs = root.querySelectorAll('input');
  inputs[1].value = 'التقارير';
  inputs[1].dispatchEvent(new TestEvent('input', { bubbles: true }));

  assert.deepEqual(seen, [['ar', 'التقارير']]);
  assert.equal(commits, 1);
});
