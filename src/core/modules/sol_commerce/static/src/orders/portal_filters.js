document.addEventListener("change", (event) => {
  const select = event.target.closest("select.o_medilab_catalog_filter");
  if (select?.form) {
    select.form.requestSubmit();
  }
});
