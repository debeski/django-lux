// Search-and-select fields: a name box that fills a hidden foreign key.
//
// The suggestions are drawn here rather than left to <datalist>, for two
// reasons. A datalist matches the text you typed against the start of an option
// in most browsers, and nearly every supplier here begins with the same word —
// so typing the part that identifies one matched nothing. And a datalist can
// only match text it contains, while the whole point of this field is to offer
// the entry you *meant* when what you typed is not quite any of them.
//
// The ranking mirrors the server's: whole-string closeness, and closeness of
// the distinctive words with the register's boilerplate set aside. The server
// still decides — this is a convenience, and a form posted without it resolves
// identically.
(function () {
    'use strict';

    const MAX_SUGGESTIONS = 8;
    const SHARE_DEFAULT = 0.15;
    const NEAR_DEFAULT = 0.90;
    const BOILERPLATE_SHARE = SHARE_DEFAULT;

    // Mirrors `dlux.lookup.normalize`, folding included. Without the folding
    // the ranking disagreed with the server on the commonest Arabic variant:
    // the server reused the record exactly while the box cleared its key and
    // offered the same name back as a guess.
    const EQUIVALENTS = { '\u0623': '\u0627', '\u0625': '\u0627', '\u0622': '\u0627', '\u0671': '\u0627', '\u0629': '\u0647', '\u0649': '\u064a', '\u0640': '' };

    function normalize(value) {
        return (value || '').trim().replace(/\s+/g, ' ').toLowerCase()
            .replace(/[\u0623\u0625\u0622\u0671\u0629\u0649\u0640]/g, function (ch) {
                return EQUIVALENTS[ch];
            })
            .replace(/[\u064b-\u0652]/g, '');
    }

    // Longest-common-subsequence ratio: the same shape as difflib's, close
    // enough for ordering a list the server will re-check anyway.
    function ratio(a, b) {
        if (!a.length || !b.length) return 0;
        const rows = a.length + 1;
        const cols = b.length + 1;
        let previous = new Array(cols).fill(0);
        let current = new Array(cols).fill(0);
        for (let i = 1; i < rows; i += 1) {
            for (let j = 1; j < cols; j += 1) {
                current[j] = a[i - 1] === b[j - 1]
                    ? previous[j - 1] + 1
                    : Math.max(previous[j], current[j - 1]);
            }
            previous = current;
            current = new Array(cols).fill(0);
        }
        return (2 * previous[cols - 1]) / (a.length + b.length);
    }

    function boilerplate(names) {
        const counts = new Map();
        names.forEach(function (name) {
            new Set(normalize(name).split(' ')).forEach(function (word) {
                counts.set(word, (counts.get(word) || 0) + 1);
            });
        });
        const floor = Math.max(3, names.length * BOILERPLATE_SHARE);
        const common = new Set();
        counts.forEach(function (count, word) {
            if (count >= floor) common.add(word);
        });
        return common;
    }

    function distinctive(name, common) {
        const words = normalize(name).split(' ').filter(function (word) {
            return !common.has(word);
        });
        return words.length ? words.join(' ') : normalize(name);
    }

    function bind(root) {
        if (root.dataset.lookupBound === '1') return;
        root.dataset.lookupBound = '1';

        const input = root.querySelector('[data-lookup-text]');
        const hidden = root.querySelector('[data-lookup-value]');
        const typed = root.querySelector('[data-lookup-typed]');
        const source = Array.from(root.querySelectorAll('[data-lookup-options] option'));
        if (!input) return;

        const entries = source.map(function (option) {
            return { id: option.dataset.id || '', name: option.value };
        });
        const common = boilerplate(entries.map(function (entry) { return entry.name; }));

        // The field's own threshold, not a constant: raising it is how a
        // project says "stop guessing so eagerly", and that has to show while
        // typing, not only in what the server refuses afterwards.
        const nearRatio = parseFloat(root.dataset.lookupRatio || '') || NEAR_DEFAULT;
        const menu = document.createElement('div');
        menu.className = 'dropdown-menu w-100 shadow-sm lookup-suggestions';
        menu.setAttribute('role', 'listbox');
        root.appendChild(menu);

        function close() { menu.classList.remove('show'); }

        function choose(entry) {
            input.value = entry.name;
            if (hidden) hidden.value = entry.id;
            if (typed) typed.value = entry.name;
            close();
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function rank(typed) {
            const wanted = normalize(typed);
            const wantedDistinct = distinctive(typed, common);
            return entries
                .map(function (entry) {
                    const name = normalize(entry.name);
                    // A name that contains what was typed is what the reader is
                    // scanning for, so it outranks anything merely similar.
                    const contains = name.indexOf(wanted) !== -1 ? 1 : 0;
                    const score = Math.max(
                        ratio(wanted, name),
                        ratio(wantedDistinct, distinctive(entry.name, common)));
                    return { entry: entry, contains: contains, score: score };
                })
                // A row containing what was typed is search and always shows.
                // A row merely close to it is a guess, and only worth making
                // at the same closeness the server would refuse a name for.
                .filter(function (row) { return row.contains || row.score >= nearRatio; })
                .sort(function (a, b) {
                    return (b.contains - a.contains) || (b.score - a.score);
                })
                .slice(0, MAX_SUGGESTIONS);
        }

        function render() {
            if (typed) typed.value = input.value;
            if (hidden) {
                const exact = entries.find(function (entry) {
                    return normalize(entry.name) === normalize(input.value);
                });
                // Cleared when it no longer matches: an id left behind is the
                // one way this could save a party nobody chose.
                hidden.value = exact ? exact.id : '';
            }
            if (!normalize(input.value)) { close(); return; }
            const rows = rank(input.value);
            menu.innerHTML = '';
            rows.forEach(function (row) {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'dropdown-item text-truncate';
                item.setAttribute('role', 'option');
                item.textContent = row.entry.name;
                if (!row.contains) {
                    // Not what they typed, but what they may have meant.
                    item.classList.add('fst-italic');
                }
                item.addEventListener('mousedown', function (event) {
                    event.preventDefault();
                    choose(row.entry);
                });
                menu.appendChild(item);
            });
            menu.classList.toggle('show', rows.length > 0);
        }

        input.addEventListener('input', render);
        input.addEventListener('focus', render);
        input.addEventListener('blur', function () { window.setTimeout(close, 120); });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') close();
        });
        render();
    }

    function closest(node, attr) {
        let current = node;
        while (current && current !== document) {
            if (current.dataset && attr in current.dataset) return current;
            current = current.parentElement;
        }
        return null;
    }

    // Everything below is delegated on the document rather than attached per
    // panel, because a panel is not always present when a scan runs. A refused
    // submit inside a modal re-injects the body with no `shown.bs.modal` to hang
    // a rescan on — which left the near-match suggestion inert, and the
    // typeahead with it. Reaching the field is what binds it.
    document.addEventListener('focusin', function (event) {
        const field = closest(event.target, 'lookupText');
        const root = field && closest(field, 'dluxLookup');
        if (root) bind(root);
    });

    document.addEventListener('click', function (event) {
        const pick = closest(event.target, 'lookupPick');
        if (!pick) return;
        const root = closest(pick, 'dluxLookup');
        if (!root) return;
        const input = root.querySelector('[data-lookup-text]');
        const hidden = root.querySelector('[data-lookup-value]');
        const typed = root.querySelector('[data-lookup-typed]');
        const consentField = root.querySelector('[data-lookup-confirm]');
        const consentBox = root.querySelector('[data-lookup-consent]');
        if (input) {
            input.value = pick.textContent.trim();
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
        if (typed) typed.value = pick.textContent.trim();
        // Set from the panel rather than left to `render()`, which only finds a
        // key for a name the rows carry — true today, and not worth depending on.
        if (hidden) hidden.value = pick.dataset.lookupPickId || '';
        // Taking the suggestion answers the question, so the consent goes back.
        if (consentField) consentField.value = '';
        if (consentBox) consentBox.checked = false;
    });

    document.addEventListener('change', function (event) {
        const box = closest(event.target, 'lookupConsent');
        if (!box) return;
        const root = closest(box, 'dluxLookup');
        const consentField = root && root.querySelector('[data-lookup-confirm]');
        if (consentField) consentField.value = box.checked ? 'on' : '';
    });

    function scan(root) {
        (root || document).querySelectorAll('[data-dlux-lookup]').forEach(bind);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { scan(document); });
    } else {
        scan(document);
    }
    document.addEventListener('shown.bs.modal', function (event) { scan(event.target); });
    // The dialog opening and its content arriving are two different moments;
    // the fetch that fills a dynamic modal usually lands after the first.
    document.addEventListener('dlux:modal-content-loaded', function (event) { scan(event.target); });
})();
