/* colleras.html */
if (document.documentElement.dataset.page === 'colleras') {

    (() => {
        const inputs = [...document.querySelectorAll('#worker-list input[type="checkbox"]')];
        const status = document.getElementById('selection-status');
        const updateSelection = () => {
            const selected = inputs.filter(input => input.checked).length;
            status.textContent = `${selected} de 2 seleccionados`;
            status.className = `selection-status badge ${selected === 2 ? 'text-bg-success' : selected > 2 ? 'text-bg-danger' : 'text-bg-secondary'}`;
            inputs.forEach(input => { input.disabled = selected >= 2 && !input.checked; });
        };
        inputs.forEach(input => input.addEventListener('change', updateSelection));
        updateSelection();
    })();

}

/* crear_cuenta.html */
if (document.documentElement.dataset.page === 'crear-cuenta') {

    const tipoCuenta = document.getElementById('id_rol');
    const campoCollera = document.getElementById('campo-collera');
    const codigoCollera = document.getElementById('id_collera_id');
    const campoCuadrilla = document.getElementById('campo-cuadrilla');
    const codigoCuadrilla = document.getElementById('id_cuadrilla_id');

    function actualizarCollera() {
        const esTrabajador = tipoCuenta.value === 'trabajador';
        campoCollera.hidden = !esTrabajador;
        codigoCollera.disabled = !esTrabajador;
        const usaCuadrilla = !['recursos_humanos', 'gerencia', 'cuenta_plenillera'].includes(tipoCuenta.value);
        campoCuadrilla.hidden = !usaCuadrilla;
        codigoCuadrilla.disabled = !usaCuadrilla;
    }

    tipoCuenta.addEventListener('change', actualizarCollera);
    actualizarCollera();

}

/* password_toggle.html */
if (document.querySelector('[data-password-toggle]')) {

    document.querySelectorAll('[data-password-toggle]').forEach(function (button) {
        button.addEventListener('click', function () {
            const input = document.getElementById(button.getAttribute('aria-controls'));
            const mostrar = input.type === 'password';
            input.type = mostrar ? 'text' : 'password';
            button.textContent = mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña';
            button.setAttribute('aria-pressed', String(mostrar));
        });
    });

}

document.querySelectorAll('[data-confirm]').forEach(function (element) {
    element.addEventListener('click', function (event) {
        if (!window.confirm(element.dataset.confirm)) event.preventDefault();
    });
});
document.querySelectorAll('[data-print]').forEach(function (element) {
    element.addEventListener('click', function () { window.print(); });
});
