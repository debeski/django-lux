// Loads the real login.js and prints what `dluxLoginMarkdown()` makes of hero
// messages, as JSON for `test_js_output_escaping.py`.
import fs from 'node:fs';
import vm from 'node:vm';

const context = {
    console,
    document: { addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);

const render = (text) => vm.runInContext(`dluxLoginMarkdown(${JSON.stringify(text)})`, context);
process.stdout.write(JSON.stringify({
    breakout: render('[x](https://a" onmouseover="window.__fired=1" x=")'),
    link: render('[Docs](https://example.org/a?b=1)'),
    quotes: render(`Say "hi" and it's **fine**`),
}));
