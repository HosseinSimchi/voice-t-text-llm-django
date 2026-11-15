(function () {
  "use strict";
  var form = document.getElementById("upload-form");
  if (!form) return;
  var input = document.getElementById("file");
  var drop = document.getElementById("dropzone");
  var info = document.getElementById("file-info");
  var fileError = document.getElementById("file-error");
  var email = document.getElementById("email");
  var emailError = document.getElementById("email-error");
  var formError = document.getElementById("form-error");
  var submit = document.getElementById("submit");
  var wrap = document.getElementById("progress-wrap");
  var bar = document.getElementById("progress-bar");
  var ptext = document.getElementById("progress-text");
  var maxBytes = parseInt(form.dataset.maxBytes, 10);
  var maxMb = form.dataset.maxMb;
  var allowed = form.dataset.accept.split(",");
  var selected = null;
  var faDigits = function (s) { return String(s).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); };

  function show(el, text) { el.textContent = text; el.classList.toggle("hidden", !text); }

  function humanSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + " MB";
    return (bytes / 1073741824).toFixed(2) + " GB";
  }

  function validateFile(file) {
    if (!file) return "لطفاً یک فایل ZIP یا RAR انتخاب کنید.";
    var name = file.name.toLowerCase();
    if (!allowed.some(function (ext) { return name.endsWith(ext); })) return "فقط فایل‌های ZIP و RAR پذیرفته می‌شوند.";
    if (file.size === 0) return "فایل انتخاب‌شده خالی است.";
    if (file.size > maxBytes) return "حجم فایل بیش از " + faDigits(maxMb) + " مگابایت است.";
    return "";
  }

  function validateEmail() {
    var v = email.value.trim();
    var ok = v.length > 0 && v.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) && email.checkValidity();
    show(emailError, ok ? "" : "لطفاً یک آدرس ایمیل معتبر وارد کنید.");
    return ok;
  }

  function choose(file) {
    selected = file || null;
    var err = validateFile(selected);
    show(fileError, err);
    if (selected) show(info, selected.name + " — " + humanSize(selected.size)); else show(info, "");
    return !err;
  }

  drop.addEventListener("click", function () { input.click(); });
  drop.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", function () { choose(input.files[0]); });
  ["dragenter", "dragover"].forEach(function (t) {
    drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.add("border-blue-500", "bg-blue-50"); });
  });
  ["dragleave", "drop"].forEach(function (t) {
    drop.addEventListener(t, function (e) { e.preventDefault(); drop.classList.remove("border-blue-500", "bg-blue-50"); });
  });
  drop.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) choose(e.dataTransfer.files[0]);
  });
  email.addEventListener("blur", validateEmail);

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    show(formError, "");
    var fileOk = choose(selected || input.files[0]);
    var emailOk = validateEmail();
    if (!fileOk || !emailOk) return;

    var data = new FormData();
    data.append("file", selected);
    data.append("email", email.value.trim());
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action);
    xhr.setRequestHeader("X-CSRFToken", form.querySelector("[name=csrfmiddlewaretoken]").value);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.addEventListener("progress", function (ev) {
      if (!ev.lengthComputable) return;
      var pct = Math.round((ev.loaded / ev.total) * 100);
      bar.style.width = pct + "%";
      ptext.textContent = faDigits(pct) + "٪";
    });
    xhr.onload = function () {
      var body = {};
      try { body = JSON.parse(xhr.responseText); } catch (err) { /* non-JSON */ }
      if (xhr.status === 202 && body.redirect) { window.location.assign(body.redirect); return; }
      submit.disabled = false;
      wrap.classList.add("hidden");
      var msg = "بارگذاری انجام نشد.";
      if (xhr.status === 429) msg = "تعداد درخواست‌ها بیش از حد مجاز است. لطفاً بعداً تلاش کنید.";
      else if (xhr.status === 413) msg = "حجم فایل بیش از حد مجاز است.";
      else if (body.error) msg += " " + (body.error.message || "");
      show(formError, msg);
    };
    xhr.onerror = function () {
      submit.disabled = false;
      wrap.classList.add("hidden");
      show(formError, "خطا در ارتباط با سرور. لطفاً دوباره تلاش کنید.");
    };
    submit.disabled = true;
    wrap.classList.remove("hidden");
    xhr.send(data);
  });
})();
