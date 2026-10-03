document.addEventListener('DOMContentLoaded', function () {
    const overlay = document.getElementById('deleteModalOverlay');
    const form = document.getElementById('deleteModalForm');
    const messageEl = document.getElementById('deleteModalMessage');
    const cancelBtn = document.getElementById('deleteModalCancel');

    if (!overlay || !form || !messageEl || !cancelBtn) {
        return;
    }

    let activeBtn = null;

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
            activeBtn = btn;
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

    // Delete without leaving the page: POST in the background, alert the
    // server's message, and drop the row from the table in place.
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const url = form.action;

        fetch(url, {
            method: 'POST',
            body: new FormData(form),
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
        })
            .then(function (res) {
                if (!res.ok) {
                    throw new Error('HTTP ' + res.status);
                }
                return res.json();
            })
            .then(function (data) {
                closeModal();
                alert(data.message);
                if (data.ok && activeBtn) {
                    const row = activeBtn.closest('tr');
                    if (row) {
                        row.remove();
                    }
                }
                activeBtn = null;
            })
            .catch(function () {
                // Not JSON (e.g. session expired -> login page). Fall back to
                // a regular full-page POST so the server flow takes over.
                form.action = url;
                form.submit();
            });
    });
});