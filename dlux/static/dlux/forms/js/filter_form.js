document.addEventListener('change', function (event) {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
        return;
    }

    const form = target.closest('form.dlux-filter[data-dlux-filter-autosubmit="true"]');
    if (!form) {
        return;
    }
    if (target.multiple || target.disabled || target.dataset.dluxNoAutosubmit === 'true') {
        return;
    }

    form.submit();
});
