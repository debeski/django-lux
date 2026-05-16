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

    function microsysDatepickerOptions() {
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

    window.initMicrosysDatepickers = function (scope) {
        if (!window.Datepicker) {
            return;
        }

        const root = scope || document;
        root.querySelectorAll('.ms-datepicker, .flatpickr').forEach(function (input) {
            if (!(input instanceof HTMLInputElement) || input.type === 'hidden') {
                return;
            }
            if (input.dataset.msDatepickerReady === 'true') {
                return;
            }
            input.setAttribute('autocomplete', 'off');
            input.dataset.msDatepickerReady = 'true';
            new Datepicker(input, microsysDatepickerOptions());
        });
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-inline-width]').forEach(function (element) {
            element.style.width = element.dataset.inlineWidth || '';
        });

        window.initMicrosysDatepickers(document);

        document.querySelectorAll(".alert:not([data-autoclose='false'])").forEach(function (message) {
            setTimeout(function () {
                message.style.opacity = '0';
                setTimeout(function () {
                    message.remove();
                }, 3000);
            }, 3000);
        });
    });
})();
