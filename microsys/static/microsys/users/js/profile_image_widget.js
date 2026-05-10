document.addEventListener('change', function (event) {
    const fileInput = event.target;
    if (!(fileInput instanceof HTMLInputElement) || !fileInput.matches('.ms-profile-file-input')) {
        return;
    }

    const file = fileInput.files && fileInput.files[0];
    const previewTargetId = fileInput.dataset.previewTarget;
    const previewElement = previewTargetId ? document.getElementById(previewTargetId) : null;

    if (!file || !previewElement) {
        return;
    }

    const reader = new FileReader();
    reader.onload = function (loadEvent) {
        const result = loadEvent.target && loadEvent.target.result;
        if (!result) {
            return;
        }

        if (previewElement.tagName === 'IMG') {
            previewElement.src = result;
            return;
        }

        const image = document.createElement('img');
        image.src = result;
        image.className = 'ms-image-preview-circle';
        image.id = previewElement.id;
        previewElement.parentNode.replaceChild(image, previewElement);
    };
    reader.readAsDataURL(file);
});
