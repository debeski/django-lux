document.addEventListener('DOMContentLoaded', function() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            // Check if form is valid (if using browser validation)
            if (!form.checkValidity()) {
                return;
            }

            if (form.dataset.dluxSubmitting === 'true') {
                event.preventDefault();
                return;
            }
            form.dataset.dluxSubmitting = 'true';

            // Preserve which named action triggered a multi-button form.
            const submitBtn = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) {
                // Disabling a named submitter inside the submit event removes its
                // name/value from native form serialization. Defer that mutation.
                window.setTimeout(() => {
                    submitBtn.disabled = true;
                    submitBtn.classList.add('disabled');
                }, 0);
                
                window.setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.classList.remove('disabled');
                    delete form.dataset.dluxSubmitting;
                }, 5000);
            } else {
                window.setTimeout(() => {
                    delete form.dataset.dluxSubmitting;
                }, 5000);
            }
        });
    });
});
