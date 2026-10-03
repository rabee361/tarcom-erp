// Behaviour for the image uploader slots rendered by
// dashboard/partials/img_upload_slot.html. Each slot wraps a Django
// ClearableFileInput; the native widget is hidden (img_uploader.css) and this
// script drives the visual preview and the removal toggle.
(function () {
    'use strict';

    function fileInput(slot) {
        return slot.querySelector('input[type="file"]');
    }

    function clearCheckbox(slot) {
        return slot.querySelector('input[type="checkbox"][name$="-clear"]');
    }

    function showImage(slot, url) {
        slot.querySelector('.img-slot-thumb').src = url;
        slot.classList.add('has-image');
        slot.classList.remove('is-removing');
        const box = clearCheckbox(slot);
        if (box) {
            box.checked = false;
        }
    }

    function markForRemoval(slot) {
        const input = fileInput(slot);
        if (input) {
            input.value = ''; // drop any newly picked file
        }
        const box = clearCheckbox(slot);
        if (box) {
            // Saved image: Django clears it server-side when this is checked.
            box.checked = true;
            slot.classList.add('is-removing');
        } else {
            slot.classList.remove('has-image', 'is-removing');
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.img-slot').forEach(function (slot) {
            const input = fileInput(slot);
            if (!input) {
                return;
            }
            input.addEventListener('change', function () {
                const file = input.files && input.files[0];
                if (!file) {
                    return;
                }
                const reader = new FileReader();
                reader.onload = function (event) {
                    showImage(slot, event.target.result);
                };
                reader.readAsDataURL(file);
            });
            slot.querySelector('.img-slot-remove').addEventListener('click', function (event) {
                // The preview is a <label for="file-input">; keep this click
                // from opening the file picker.
                event.preventDefault();
                event.stopPropagation();
                markForRemoval(slot);
            });
        });
    });
})();