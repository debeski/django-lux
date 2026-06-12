document.addEventListener('change', function (event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }

    const form = target.closest('form.dlux-filter[data-dl-filter-autosubmit="true"]');
    if (!form) {
        return;
    }
    if (target.multiple || target.disabled || target.dataset.msNoAutosubmit === 'true') {
        return;
    }

    form.submit();
});
