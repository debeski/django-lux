/**
 * Microsys Form Wizard
 * Handles multi-step form navigation within dynamic modals.
 * Detects .wizard-step elements and manages Next/Prev/Submit button visibility.
 * Self-initializing: uses MutationObserver to detect when wizard content is loaded via AJAX.
 */

(function() {
    if (window.__msWizardInitialized) return;
    window.__msWizardInitialized = true;

    function resolveWizardForm(container) {
        if (!container) {
            return null;
        }
        if (container.matches && container.matches('form')) {
            return container;
        }
        if (container.querySelector) {
            return container.querySelector('form');
        }
        return null;
    }

    function prepareWizardContainer(container) {
        if (typeof window.__msPrepareWizardContainer !== 'function') {
            return;
        }
        window.__msPrepareWizardContainer(container);
    }

    function initWizard(container) {
        const steps = container.querySelectorAll('.wizard-step');
        if (steps.length < 2) return;

        const btnNext = container.querySelector('.ms-btn-next');
        const btnPrev = container.querySelector('.ms-btn-prev');
        const btnSubmit = container.querySelector('.ms-btn-submit');
        const stepNavItems = Array.from(container.querySelectorAll('[data-ms-wizard-step-target]'));

        if (!btnNext || !btnPrev || !btnSubmit) return;

        // Prevent double-binding
        if (container.dataset.msWizardBound === 'true') return;
        prepareWizardContainer(container);
        container.dataset.msWizardBound = 'true';

        let currentStep = 0;
        let resolvedStep = null;
        const wizardForm = resolveWizardForm(container);
        if (typeof window.__msGetWizardInitialStep === 'function') {
            const setupStep = window.__msGetWizardInitialStep(container);
            if (setupStep !== null && setupStep !== undefined && setupStep !== '') {
                const candidate = Number(setupStep);
                if (Number.isInteger(candidate) && candidate >= 0 && candidate < steps.length) {
                    resolvedStep = candidate;
                }
            }
        }
        if (resolvedStep === null) {
            const initialStepSource = container.dataset.msWizardInitialStep || (wizardForm && wizardForm.dataset.msWizardInitialStep);
            const candidate = Number(initialStepSource);
            if (Number.isInteger(candidate) && candidate >= 0 && candidate < steps.length) {
                resolvedStep = candidate;
            }
        }
        if (resolvedStep !== null) {
            currentStep = resolvedStep;
        }

        function setButtonVisibility(button, isVisible) {
            if (!button) {
                return;
            }
            button.classList.toggle('d-none', !isVisible);
            button.style.display = isVisible ? '' : 'none';
            button.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
        }

        function syncStepNav(index) {
            stepNavItems.forEach(function(item) {
                const target = Number(item.dataset.msWizardStepTarget);
                const isActive = target === index;
                const isComplete = Number.isInteger(target) && target < index;
                item.classList.toggle('is-active', isActive);
                item.classList.toggle('is-complete', isComplete);
                item.setAttribute('aria-current', isActive ? 'step' : 'false');
            });
        }

        function showStep(index) {
            steps.forEach(function(step, i) {
                const isActive = i === index;
                step.classList.toggle('d-none', !isActive);
                step.style.display = isActive ? '' : 'none';
                step.setAttribute('aria-hidden', isActive ? 'false' : 'true');
            });

            // Button visibility
            setButtonVisibility(btnPrev, index !== 0);
            setButtonVisibility(btnNext, index !== steps.length - 1);
            setButtonVisibility(btnSubmit, index === steps.length - 1);

            currentStep = index;
            syncStepNav(index);
            container.dispatchEvent(new CustomEvent('ms:wizard-step-change', {
                bubbles: true,
                detail: {
                    currentStep: index,
                    totalSteps: steps.length
                }
            }));
        }

        stepNavItems.forEach(function(item) {
            item.addEventListener('click', function() {
                const target = Number(item.dataset.msWizardStepTarget);
                if (Number.isInteger(target) && target >= 0 && target < steps.length) {
                    showStep(target);
                }
            });
        });

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

        showStep(currentStep);
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
