(function () {
    'use strict';

    function ensureArabicDatepickerLocale() {
        if (!window.Datepicker || !window.Datepicker.locales) {
            return;
        }

        if (!window.Datepicker.locales.ar) {
            window.Datepicker.locales.ar = {
                days: ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'],
                daysShort: ['أحد', 'إثن', 'ثلا', 'أرب', 'خم', 'جم', 'سبت'],
                daysMin: ['ح', 'ن', 'ث', 'ر', 'خ', 'ج', 'س'],
                months: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'],
                monthsShort: ['ينا', 'فبر', 'مار', 'أبر', 'ماي', 'يون', 'يول', 'أغس', 'سبت', 'أكت', 'نوف', 'ديس'],
                today: 'اليوم',
                clear: 'مسح',
                titleFormat: 'MM y',
            };
        }
    }

    function dluxDatepickerOptions() {
        const options = {
            format: 'yyyy-mm-dd',
            autohide: true,
            buttonClass: 'btn',
        };

        if ((document.documentElement.getAttribute('lang') || 'en') === 'ar') {
            ensureArabicDatepickerLocale();
            options.language = 'ar';
        }

        return options;
    }

    window.initDluxDatepickers = function (scope) {
        if (!window.Datepicker) {
            return;
        }

        const root = scope || document;
        root.querySelectorAll('.dlux-datepicker, .flatpickr').forEach(function (input) {
            if (!(input instanceof HTMLInputElement) || input.type === 'hidden') {
                return;
            }
            if (input.dataset.dluxDatepickerReady === 'true') {
                return;
            }
            input.setAttribute('autocomplete', 'off');
            input.dataset.dluxDatepickerReady = 'true';
            new Datepicker(input, dluxDatepickerOptions());
        });
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-inline-width]').forEach(function (element) {
            element.style.width = element.dataset.inlineWidth || '';
        });

        window.initDluxDatepickers(document);

        function closeAlert(message) {
            if (!message || !message.isConnected) {
                return;
            }
            message.classList.add('dlux-alert--closing');
            message.setAttribute('aria-hidden', 'true');
            setTimeout(function () {
                if (message.isConnected) {
                    message.remove();
                }
            }, 260);
        }

        // Auto-hide is OPT-IN, not the default. Only alerts explicitly marked
        // data-autohide="true" fade out on their own. The Dlux flash/notification
        // template stamps that attribute on its messages, so real notifications
        // still auto-dismiss — but every other .alert on the page (modal notices,
        // form warnings, inline hints) now stays until the user dismisses it, with
        // no opt-out attribute needed. data-autoclose="false" still force-pins an
        // alert that would otherwise auto-hide (kept for backward compatibility).
        document.querySelectorAll('.alert[data-autohide="true"]:not([data-autoclose="false"])').forEach(function (message) {
            const container = message.closest('[data-dlux-flash-timeout]');
            const configuredTimeout = container ? parseInt(container.dataset.dluxFlashTimeout || '', 10) : NaN;
            const timeout = Number.isFinite(configuredTimeout) ? configuredTimeout : 3200;
            if (timeout <= 0) {
                return;
            }
            setTimeout(function () {
                closeAlert(message);
            }, timeout);
        });
    });
})();
