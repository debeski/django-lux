document.addEventListener('DOMContentLoaded', function () {
    [
        ['id_type', 'id_name'],
        ['id_subtype', 'id_subname'],
    ].forEach(function ([sourceId, targetId]) {
        const source = document.getElementById(sourceId);
        const target = document.getElementById(targetId);

        if (!source || !target) {
            return;
        }

        source.addEventListener('change', function () {
            const label = source.options[source.selectedIndex]?.text || '';
            target.value = `${label} `;
            target.focus();
            target.setSelectionRange(target.value.length, target.value.length);
        });
    });

    if (typeof window.initMicrosysDatepickers === 'function') {
        window.initMicrosysDatepickers(document);
    }

    if (window.bootstrap && window.bootstrap.Tooltip) {
        document.querySelectorAll('.subsection-help[data-bs-toggle="tooltip"]').forEach(function (element) {
            window.bootstrap.Tooltip.getOrCreateInstance(element, { container: 'body' });
        });
    }
});
