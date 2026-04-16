document.addEventListener('DOMContentLoaded', function() {
    // Auto-submit filters on change
    const autoSubmitElements = document.querySelectorAll('.auto-submit-filter');
    autoSubmitElements.forEach(element => {
        element.addEventListener('change', function() {
            this.form.submit();
        });
    });
});
