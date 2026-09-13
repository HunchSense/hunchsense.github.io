(function () {
  "use strict";

  var script = document.currentScript || document.querySelector("script[data-endpoint]");
  var endpoint = script && script.dataset.endpoint;
  var mounted = false;

  function addField(form) {
    if (form.elements.message) return;
    var actions = form.querySelector(".form-actions");
    if (!actions) return;

    var field = document.createElement("div");
    field.className = "field contact-message-field";
    var label = document.createElement("label");
    label.htmlFor = "message";
    label.textContent = "What are you working on?";
    var textarea = document.createElement("textarea");
    textarea.id = "message";
    textarea.name = "message";
    textarea.rows = 4;
    textarea.maxLength = 2000;
    textarea.placeholder = "Which instruments are you using, and what do you need to measure or control?";
    textarea.required = true;
    field.append(label, textarea);
    actions.before(field);

    var trap = document.createElement("input");
    trap.type = "text";
    trap.name = "website";
    trap.tabIndex = -1;
    trap.autocomplete = "off";
    trap.setAttribute("aria-hidden", "true");
    trap.className = "contact-form-trap";
    form.append(trap);
  }

  function statusElement(form) {
    var status = form.querySelector(".contact-form-status");
    if (!status) {
      status = document.createElement("div");
      status.className = "contact-form-status";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      form.append(status);
    }
    return status;
  }

  function setStatus(form, type, message) {
    var status = statusElement(form);
    status.className = "contact-form-status " + type;
    status.textContent = message;
  }

  async function submit(event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || form.id !== "demo-form") return;
    event.preventDefault();
    event.stopImmediatePropagation();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    if (!endpoint) {
      setStatus(form, "error", "The form is unavailable right now. Email Chris or Shawn instead.");
      return;
    }

    var button = form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    button.disabled = true;
    button.textContent = "Sending...";
    form.setAttribute("aria-busy", "true");
    setStatus(form, "pending", "Sending...");

    var data = new FormData(form);
    var payload = {
      name: String(data.get("name") || ""),
      email: String(data.get("email") || ""),
      company: String(data.get("company") || ""),
      role: String(data.get("role") || ""),
      message: String(data.get("message") || ""),
      website: String(data.get("website") || ""),
      request_id: typeof crypto.randomUUID === "function" ? crypto.randomUUID() : "",
    };

    var controller = typeof AbortController === "function" ? new AbortController() : null;
    var timeout = controller ? window.setTimeout(function () { controller.abort(); }, 12000) : null;

    try {
      var response = await fetch(endpoint, {
        method: "POST",
        // text/plain is CORS-safelisted, so browser extensions and stricter
        // clients cannot strand the submission after an OPTIONS preflight.
        headers: { "Content-Type": "text/plain;charset=UTF-8" },
        body: JSON.stringify(payload),
        credentials: "omit",
        signal: controller ? controller.signal : undefined,
      });
      var result = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(result.message || "Request could not be delivered.");
      form.reset();
      button.textContent = "Request received";
      setStatus(form, "success", "Thanks. Chris or Shawn will reply within one business day.");
    } catch (error) {
      button.disabled = false;
      button.textContent = "Book a demo";
      var message = error instanceof Error ? error.message : "";
      if (!message || message === "Failed to fetch" || (error && error.name === "AbortError")) {
        message = "The form could not send your request. Try again, or email Chris or Shawn directly.";
      }
      setStatus(form, "error", message);
    } finally {
      if (timeout) window.clearTimeout(timeout);
      form.removeAttribute("aria-busy");
    }
  }

  function mount() {
    if (mounted) return;
    var form = document.getElementById("demo-form");
    if (!form) return;
    mounted = true;
    addField(form);
    document.addEventListener("submit", submit, true);
  }

  var observer = new MutationObserver(function () {
    mount();
    if (mounted) observer.disconnect();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
})();
