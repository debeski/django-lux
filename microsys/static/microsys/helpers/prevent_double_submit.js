document.addEventListener('DOMContentLoaded', function() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Check if form is valid (if using browser validation)
            if (!form.checkValidity()) {
                return;
            }

            // Find submit button
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) {
                // Add loading spinner or text if desired, or just disable
                const originalText = submitBtn.innerHTML;
                submitBtn.disabled = true;
                submitBtn.classList.add('disabled');
                
                // Optional: Change text to indicate processing
                // submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';

                // Re-enable after a timeout (fallback in case of error/no navigation)
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.classList.remove('disabled');
                    // submitBtn.innerHTML = originalText;
                }, 5000); // 5 seconds timeout
            }
        });
    });
});
