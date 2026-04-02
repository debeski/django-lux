/**
 * Microsys Form Wizard
 * Handles multi-step form navigation within dynamic modals.
 * Detects .wizard-step elements and manages Next/Prev/Submit button visibility.
 * Self-initializing: uses MutationObserver to detect when wizard content is loaded via AJAX.
 */

(function() {
    if (window.__msWizardInitialized) return;
    window.__msWizardInitialized = true;

    function initWizard(container) {
        const steps = container.querySelectorAll('.wizard-step');
        if (steps.length < 2) return;

        const btnNext = container.querySelector('.ms-btn-next');
        const btnPrev = container.querySelector('.ms-btn-prev');
        const btnSubmit = container.querySelector('.ms-btn-submit');

        if (!btnNext || !btnPrev || !btnSubmit) return;

        // Prevent double-binding
        if (container.dataset.msWizardBound === 'true') return;
        container.dataset.msWizardBound = 'true';

        let currentStep = 0;

        function showStep(index) {
            steps.forEach(function(step, i) {
                step.style.display = (i === index) ? '' : 'none';
            });

            // Button visibility
            btnPrev.style.display = (index === 0) ? 'none' : '';
            btnNext.style.display = (index === steps.length - 1) ? 'none' : '';
            btnSubmit.style.display = (index === steps.length - 1) ? '' : 'none';

            currentStep = index;
        }

        btnNext.addEventListener('click', function() {
            // Validate visible required fields in the current step before proceeding
            var currentStepEl = steps[currentStep];
            var inputs = currentStepEl.querySelectorAll('input, select, textarea');
            var valid = true;

            inputs.forEach(function(input) {
                if (!input.checkValidity()) {
                    input.reportValidity();
                    valid = false;
                }
            });

            if (valid && currentStep < steps.length - 1) {
                showStep(currentStep + 1);
            }
        });

        btnPrev.addEventListener('click', function() {
            if (currentStep > 0) {
                showStep(currentStep - 1);
            }
        });

        // Initialize on Step 1
        showStep(0);
    }

    // Auto-initialize for any wizard steps already in the DOM
    function scanAndInit() {
        // Look for forms or containers that have wizard steps
        var containers = document.querySelectorAll('form, .modal-body');
        containers.forEach(function(container) {
            if (container.querySelector('.wizard-step') && container.dataset.msWizardBound !== 'true') {
                initWizard(container);
            }
        });
    }

    // Run on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', scanAndInit);

    // Use MutationObserver to detect AJAX-loaded content (dynamic modals)
    var observer = new MutationObserver(function(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var mutation = mutations[i];
            for (var j = 0; j < mutation.addedNodes.length; j++) {
                var node = mutation.addedNodes[j];
                if (node.nodeType === 1 && (node.querySelector('.wizard-step') || node.classList.contains('wizard-step'))) {
                    scanAndInit();
                    return;
                }
            }
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });

})();
