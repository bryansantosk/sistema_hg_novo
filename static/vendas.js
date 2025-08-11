function calcularTotal() {
    const checkboxes = document.querySelectorAll('.produto-checkbox');
    let total = 0.00;
    let itensSelecionados = [];

    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            const [nome, valor] = checkbox.value.split('|');
            total += parseFloat(valor);
            itensSelecionados.push(`${nome} - R$ ${parseFloat(valor).toFixed(2)}`);
        }
    });

    document.getElementById('total').value = total.toFixed(2);
    document.getElementById('itens').value = itensSelecionados.join(', ');
    return true;
}
