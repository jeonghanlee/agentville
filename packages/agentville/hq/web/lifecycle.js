// Administrator credentials live only in the closure form and its in-flight request.
import { el, button } from "./dom.js";
import { t } from "./i18n.js";

export function createLifecycle({ canClose, refresh }) {
  let busy = false;
  function action(kind, id, name, closed) {
    return button(t("lifecycle.close"), "secondary-button lifecycle-close", () => {
      if (!canClose() || closed || busy) return;
      const input = el("input", { type: "password", required: "", minlength: "16", autocomplete: "off",
        "aria-label": t("lifecycle.token") });
      const error = el("p", { role: "alert", class: "lifecycle-error" });
      const submit = el("button", { type: "submit", class: "secondary-button" }, t("lifecycle.confirm"));
      const dialog = el("dialog", { class: "lifecycle-dialog", "aria-label": t("lifecycle.close") });
      const cancel = button(t("lifecycle.cancel"), "secondary-button", () => dialog.close());
      const form = el("form", {}, el("h2", {}, name), el("p", {}, t("lifecycle.help")),
        el("label", {}, t("lifecycle.token"), input), error, el("div", {}, cancel, submit));
      dialog.append(form);
      dialog.addEventListener("close", () => { input.value = ""; dialog.remove(); });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!canClose() || busy) return;
        busy = true; submit.disabled = true;
        const credential = input.value;
        input.value = "";
        try {
          const response = await fetch("/api/v1/lifecycle/close", { method: "POST", cache: "no-store",
            headers: { "Content-Type": "application/json", Authorization: "Bearer " + credential },
            body: JSON.stringify({ kind, id }) });
          if (!response.ok) throw new Error(String(response.status));
          await refresh();
          dialog.close();
        } catch (failure) {
          error.textContent = t(failure.message === "503" ? "lifecycle.disabled" : "lifecycle.failed");
        } finally {
          busy = false; submit.disabled = false;
        }
      });
      document.body.append(dialog);
      dialog.showModal();
      input.focus();
    }, { ...(closed || !canClose() ? { disabled: "" } : {}), "data-kind": kind, "data-target": id });
  }
  return { action };
}
