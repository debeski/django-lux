// Drives the real lookup script through the paths a reader takes after a
// refused submit. Prints one JSON object; `test_lookup_js.py` asserts on it.
import { field, loadScript, report } from './harness.mjs';

const NAMES = [[75, 'التشاركية العصرية'], [12, 'شركة النور'], [40, 'Acme Trading']];

// Loaded while no lookup field is in the document, which is the case this
// exists for: the panel arrives later, injected into an open modal.
loadScript(process.argv[2]);

const results = {};

{
    const f = field({ names: NAMES, typedValue: 'التشاركية العصر', near: [75, 'التشاركية العصرية'] });
    // Reaching the box binds the typeahead, so `render()` is live when the
    // suggestion is clicked. Unbound, the ordering below cannot be seen at all.
    f.input.dispatchEvent(new Event('focusin'));
    f.confirm.value = 'on';
    f.pick.dispatchEvent(new Event('click'));
    results.pick = {
        input: f.input.value, hidden: f.hidden.value,
        typed: f.typed.value, confirm: f.confirm.value,
    };
}

{
    const f = field({ names: NAMES, typedValue: 'شركة الفجر', near: [12, 'شركة النور'] });
    f.consent.checked = true;
    f.consent.dispatchEvent(new Event('change'));
    results.consent = { confirm: f.confirm.value };
}

{
    // Search-only field: no consent box in the panel, and picking must not fail
    // for its absence.
    const f = field({
        names: NAMES, typedValue: 'Acme Trad', near: [40, 'Acme Trading'], allowCreate: false,
    });
    f.input.dispatchEvent(new Event('focusin'));
    f.pick.dispatchEvent(new Event('click'));
    results.searchOnly = { input: f.input.value, hidden: f.hidden.value };
}

{
    // The typeahead is bound by reaching the field, so an injected one works.
    const f = field({ names: NAMES, typedValue: '' });
    f.input.dispatchEvent(new Event('focusin'));
    f.input.value = 'Acme Trading';
    f.input.dispatchEvent(new Event('input'));
    const exact = f.hidden.value;
    f.input.value = 'Acme Tradin';
    f.input.dispatchEvent(new Event('input'));
    results.typeahead = { exact: exact, afterEdit: f.hidden.value };
}

{
    // The Arabic variant the server folds to an exact match must resolve to the
    // same key here, not be cleared and offered back as a guess.
    const f = field({ names: NAMES, typedValue: '' });
    f.input.dispatchEvent(new Event('focusin'));
    f.input.value = 'شركه النور';
    f.input.dispatchEvent(new Event('input'));
    results.folding = { hidden: f.hidden.value };
}

report(results);
