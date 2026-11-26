// The package page counts the chosen parameters and totals their prices as the customer ticks, adds or changes the
// quantity, so the price is shown before the package goes into the cart.
function formatPrice(amount) {
    const language = document.documentElement.lang || "vi-VN";
    return new Intl.NumberFormat(language, { style: "currency", currency: "VND" }).format(amount);
}

function refresh(page) {
    const chosen = [...page.querySelectorAll("input[name='parameter_ids']:checked")];
    const quantity = Math.max(1, Number.parseInt(page.querySelector(".o_medilab_package_quantity").value, 10) || 1);
    const total = chosen.reduce((sum, input) => sum + Number(input.dataset.price || 0), 0) * quantity;
    page.querySelector(".o_medilab_package_total").textContent = formatPrice(total);
    page.querySelector(".o_medilab_package_count").textContent = chosen.length;
    for (const button of page.querySelectorAll("button[type='submit']")) {
        button.disabled = chosen.length === 0;
    }
}

function addParameter(page) {
    const select = page.querySelector(".o_medilab_package_extra");
    const option = select.selectedOptions[0];
    if (!option?.value) {
        return;
    }
    const row = page.querySelector(".o_medilab_package_row_template").content.firstElementChild.cloneNode(true);
    const input = row.querySelector("input");
    input.value = option.value;
    input.dataset.price = option.dataset.price;
    input.setAttribute("aria-label", option.textContent);
    row.querySelector(".o_medilab_package_name").textContent = option.textContent;
    row.querySelector(".o_medilab_package_price").textContent = formatPrice(Number(option.dataset.price));
    page.querySelector(".o_medilab_package_parts").append(row);
    option.remove();
    select.value = "";
    refresh(page);
}

function start() {
    const page = document.querySelector(".o_medilab_package_page");
    if (!page) {
        return;
    }
    page.addEventListener("change", () => refresh(page));
    page.addEventListener("input", () => refresh(page));
    page.querySelector(".o_medilab_package_add")?.addEventListener("click", () => addParameter(page));
    refresh(page);
}

// The frontend bundle loads lazily, often after the page is ready.
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
} else {
    start();
}
