document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('deleteModalOverlay');
    const form = document.getElementById('deleteModalForm');
    const messageEl = document.getElementById('deleteModalMessage');
    const cancelBtn = document.getElementById('deleteModalCancel');

    if (!overlay || !form || !messageEl || !cancelBtn) {
        return;
    }

    function openModal(url, objectName) {
        form.action = url;
        messageEl.textContent = 'هل أنت متأكد من حذف "' + objectName + '"؟ لا يمكن التراجع عن هذا الإجراء.';
        overlay.hidden = false;
    }

    function closeModal() {
        overlay.hidden = true;
        form.action = '';
        messageEl.textContent = '';
    }

    document.querySelectorAll('.js-delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            openModal(btn.dataset.deleteUrl, btn.dataset.objectName);
        });
    });

    cancelBtn.addEventListener('click', closeModal);

    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
            closeModal();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !overlay.hidden) {
            closeModal();
        }
    });
});