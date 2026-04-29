(function () {
    var THEME_KEY = 'trufiq-theme';
    var THEME_HREFS = {
        'terracota-editorial': '/static/css/themes/terracota-editorial.css',
        'piedra-y-olivo': '/static/css/themes/piedra-y-olivo.css',
        'bodega-tecnica': '/static/css/themes/bodega-tecnica.css'
    };

    function applyTheme(themeName) {
        var themeLink = document.getElementById('tf-theme-link');
        var normalizedTheme = THEME_HREFS[themeName] ? themeName : 'bodega-tecnica';

        if (themeLink) {
            themeLink.setAttribute('href', THEME_HREFS[normalizedTheme]);
        }

        document.documentElement.setAttribute('data-theme', normalizedTheme);
        window.localStorage.setItem(THEME_KEY, normalizedTheme);

        document.querySelectorAll('[data-theme-select]').forEach(function (select) {
            if (select.value !== normalizedTheme) {
                select.value = normalizedTheme;
            }
        });

        document.querySelectorAll('[data-theme-button]').forEach(function (button) {
            var buttonTheme = button.getAttribute('data-theme-button');
            var isActive = buttonTheme === normalizedTheme;
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function setupThemeSwitcher() {
        var savedTheme = window.localStorage.getItem(THEME_KEY) || document.documentElement.getAttribute('data-theme') || 'bodega-tecnica';

        document.querySelectorAll('[data-theme-select]').forEach(function (select) {
            select.value = THEME_HREFS[savedTheme] ? savedTheme : 'bodega-tecnica';
            select.addEventListener('change', function () {
                applyTheme(select.value);
            });
        });

        document.querySelectorAll('[data-theme-button]').forEach(function (button) {
            button.addEventListener('click', function () {
                var selectedTheme = button.getAttribute('data-theme-button');
                applyTheme(selectedTheme);
            });
        });

        applyTheme(savedTheme);
    }

    function autoDismissFlash() {
        var flash = document.getElementById('flashMsg');
        if (!flash || !window.bootstrap) {
            return;
        }

        window.setTimeout(function () {
            var alert = bootstrap.Alert.getOrCreateInstance(flash);
            alert.close();
        }, 4000);
    }

    function setupDeleteModal() {
        var modalElement = document.getElementById('deleteModal');
        if (!modalElement || !window.bootstrap) {
            return;
        }

        var deleteForm = null;
        var deleteModal = new bootstrap.Modal(modalElement);
        var closeButton = document.getElementById('deleteModalClose');
        var cancelButton = document.getElementById('deleteModalCancel');
        var confirmButton = document.getElementById('deleteConfirmBtn');

        if (closeButton) {
            closeButton.addEventListener('click', function () {
                deleteModal.hide();
            });
        }

        if (cancelButton) {
            cancelButton.addEventListener('click', function () {
                deleteModal.hide();
            });
        }

        if (confirmButton) {
            confirmButton.addEventListener('click', function () {
                deleteModal.hide();
                if (deleteForm) {
                    deleteForm.submit();
                }
            });
        }

        window.confirmDelete = function (form) {
            deleteForm = form;
            deleteModal.show();
            return false;
        };
    }

    function setupManualTabs() {
        var tabGroups = document.querySelectorAll('[data-manual-tabs]');
        tabGroups.forEach(function (group) {
            var buttons = group.querySelectorAll('[data-bs-target]');
            var targetSelector = group.getAttribute('data-tabs-target');
            var paneRoot = targetSelector ? document.querySelector(targetSelector) : null;
            var panes = paneRoot ? paneRoot.querySelectorAll('.tab-pane') : [];

            buttons.forEach(function (button) {
                button.addEventListener('click', function (event) {
                    event.preventDefault();
                    var targetId = button.getAttribute('data-bs-target');
                    var targetPane = targetId ? document.querySelector(targetId) : null;
                    if (!targetPane) {
                        return;
                    }

                    buttons.forEach(function (item) {
                        item.classList.remove('active');
                    });
                    panes.forEach(function (pane) {
                        pane.classList.remove('show', 'active');
                    });

                    button.classList.add('active');
                    targetPane.classList.add('show', 'active');
                });
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        setupThemeSwitcher();
        autoDismissFlash();
        setupDeleteModal();
        setupManualTabs();
    });
})();
