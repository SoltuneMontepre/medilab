// The order's details page keeps what the customer enters as they go, fills the chosen contact's phone and e-mail,
// and asks for a pickup address only when the laboratory picks the samples up.
const SAVE_DELAY = 600;
let pending = null;

function saveDetails(form) {
  clearTimeout(pending);
  pending = setTimeout(() => {
    fetch(form.dataset.save, { method: "POST", body: new FormData(form), credentials: "same-origin" });
  }, SAVE_DELAY);
}

function showContact(select) {
  const option = select.selectedOptions[0];
  const card = select.form.querySelector(".o_medilab_contact_card");
  card.querySelector(".o_medilab_contact_phone").textContent = option.dataset.phone || "-";
  card.querySelector(".o_medilab_contact_email").textContent = option.dataset.email || "-";
}

function showPickup(form) {
  const pickup = form.querySelector(".o_medilab_collection_method:checked")?.value === "pickup";
  form.querySelector(".o_medilab_pickup_only").hidden = !pickup;
  form.querySelector("#collection_address").required = pickup;
}

document.addEventListener("input", (event) => {
  const form = event.target.closest("form.o_medilab_details_form");
  if (form) {
    saveDetails(form);
  }
});

document.addEventListener("change", (event) => {
  const form = event.target.closest("form.o_medilab_details_form");
  if (!form) {
    return;
  }
  if (event.target.matches(".o_medilab_contact_choice")) {
    showContact(event.target);
  }
  if (event.target.matches(".o_medilab_collection_method")) {
    showPickup(form);
  }
  saveDetails(form);
});

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form.o_medilab_details_form");
  if (form) {
    showPickup(form);
    // The chosen day shows even when it is further along the row.
    form.querySelector(".o_medilab_day_chips .btn-check:checked + label")?.scrollIntoView({ block: "nearest", inline: "center" });
  }
});
