// The cart tells the customer, as they pick a date, whether it is earlier than the standard return date and so a
// priority request.
document.addEventListener("change", (event) => {
  const input = event.target.closest(".o_medilab_requested_date input[name='requested_date']");
  const picker = input?.closest(".o_medilab_requested_date");
  const notice = picker?.querySelector(".o_medilab_priority_notice");
  if (!notice) {
    return;
  }
  // ISO dates compare in calendar order as text.
  const priority = Boolean(input.value) && input.value < picker.dataset.standard;
  notice.classList.toggle("d-none", !priority);
});
