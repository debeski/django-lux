/* Settings preview: the modal sample page opens the real dynamic modal on load,
 * with a sample form rendered under the same draft. See dlux/system/preview.py. */
(function () {
    'use strict';

    function read(id) {
        const node = document.getElementById(id);
        return node ? JSON.parse(node.textContent) : '';
    }

    window.addEventListener('load', () => {
        const url = read('dlux-preview-modal-url');
        if (!url) return;
        document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
            detail: { data: { url, title: read('dlux-preview-modal-title') } },
        }));
    });
})();
