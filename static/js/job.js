(function () {
  "use strict";
  var root = document.getElementById("job");
  if (!root) return;
  var MSG = JSON.parse(document.getElementById("messages-fa").textContent);
  var statusUrl = root.dataset.statusUrl;
  var resultsUrl = root.dataset.resultsUrl;
  var el = function (id) { return document.getElementById(id); };
  var faDigits = function (s) { return String(s).replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[d]; }); };
  var TERMINAL = ["COMPLETED", "PARTIALLY_COMPLETED", "FAILED"];
  var STAGE_FA = {
    QUEUED: "در صف پردازش", EXTRACTING: "در حال باز کردن آرشیو", TRANSCRIBING: "در حال تبدیل گفتار به متن",
    GENERATING_PDF: "در حال تولید PDF", EXTRACTING_INFORMATION: "در حال استخراج اطلاعات",
    SENDING_EMAIL: "در حال ارسال ایمیل", RETRYING: "تلاش مجدد پس از خطای موقت",
    COMPLETED: "تکمیل شد", PARTIALLY_COMPLETED: "تکمیل ناقص", FAILED: "ناموفق"
  };
  var FILE_FA = {
    PENDING: "در انتظار", PREPROCESSING: "آماده‌سازی صوت", TRANSCRIBING: "تبدیل گفتار به متن",
    GENERATING_PDF: "تولید PDF", EXTRACTING_INFORMATION: "استخراج اطلاعات", RETRYING: "تلاش مجدد",
    COMPLETED: "موفق", PARTIALLY_COMPLETED: "ناقص (PDF موجود است)", FAILED: "ناموفق", SKIPPED: "پشتیبانی نمی‌شود"
  };
  var FILE_COLOR = {
    COMPLETED: "text-green-700", PARTIALLY_COMPLETED: "text-amber-700", FAILED: "text-red-700",
    SKIPPED: "text-slate-500", RETRYING: "text-amber-700"
  };
  var delay = 2000;
  var downloads = {};
  var readyShown = 0;

  function renderFiles(files) {
    var list = el("files");
    list.textContent = "";
    files.forEach(function (f) {
      var li = document.createElement("li");
      li.className = "flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-sm";
      var name = document.createElement("span");
      name.className = "font-medium text-slate-800 break-all";
      name.setAttribute("dir", "auto");
      name.textContent = faDigits(f.index + 1) + ". " + f.filename;
      var right = document.createElement("span");
      right.className = "flex items-center gap-3";
      var st = document.createElement("span");
      st.className = FILE_COLOR[f.status] || "text-blue-700";
      st.textContent = FILE_FA[f.status] || f.status;
      if (f.error_message_fa) st.title = f.error_message_fa;
      right.appendChild(st);
      if (downloads[f.result_id]) {
        var a = document.createElement("a");
        a.href = downloads[f.result_id];
        a.className = "rounded bg-blue-700 px-2 py-1 text-xs font-semibold text-white hover:bg-blue-800";
        a.textContent = "دریافت PDF";
        right.appendChild(a);
      }
      li.appendChild(name);
      li.appendChild(right);
      if (f.error_message_fa) {
        var err = document.createElement("p");
        err.className = "w-full text-xs text-slate-500";
        err.textContent = f.error_message_fa;
        li.appendChild(err);
      }
      list.appendChild(li);
    });
  }

  function showFinal(message) {
    var box = el("final");
    var styles = {
      success: ["bg-green-50 text-green-900 border border-green-200", "✅"],
      success_local: ["bg-blue-50 text-blue-900 border border-blue-200", "ℹ️"],
      partial: ["bg-amber-50 text-amber-900 border border-amber-200", "⚠️"],
      email_failed: ["bg-amber-50 text-amber-900 border border-amber-200", "✉️"],
      failed: ["bg-red-50 text-red-900 border border-red-200", "❌"]
    }[message.kind];
    if (!styles) return;
    box.className = "mb-6 rounded-xl p-4 text-sm leading-7 " + styles[0];
    el("final-icon").textContent = styles[1];
    el("final-text").textContent = message.text || MSG[message.kind] || "";
  }

  function loadDownloads(after) {
    fetch(resultsUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data) data.results.forEach(function (r) { if (r.pdf.download_url) downloads[r.result_id] = r.pdf.download_url; });
        if (data && data.download_all_url) {
          var zip = el("zip-link");
          zip.href = data.download_all_url;
          zip.classList.remove("hidden");
          zip.classList.add("block");
        }
        after();
      })
      .catch(after);
  }

  function update(data) {
    el("progress-bar").style.width = data.progress + "%";
    el("progress-text").textContent = faDigits(data.progress) + "٪";
    el("stage-label").textContent = STAGE_FA[data.state] || data.state;
    el("c-total").textContent = faDigits(data.total_audio_files);
    el("c-ok").textContent = faDigits(data.successful_files);
    el("c-partial").textContent = faDigits(data.partial_files);
    el("c-failed").textContent = faDigits(data.failed_files);  // skipped entries are listed below
    renderFiles(data.files);
    if (TERMINAL.indexOf(data.state) !== -1) {
      // Success is announced only when the server reports COMPLETED with the e-mail accepted (message.kind).
      showFinal(data.message);
      loadDownloads(function () { renderFiles(data.files); });
      el("email-hint").classList.add("hidden");
      return true;
    }
    // Finished files can be downloaded while the rest (or the e-mail step) is still running.
    var ready = data.files.filter(function (f) { return f.status === "COMPLETED" || f.status === "PARTIALLY_COMPLETED"; }).length;
    if (ready && ready !== readyShown) {
      readyShown = ready;
      loadDownloads(function () { renderFiles(data.files); });
    }
    // 95% = the e-mail step; explain a failing delivery instead of silently waiting.
    el("email-hint").classList.toggle("hidden", !(data.state === "RETRYING" && data.progress >= 95));
    return false;
  }

  function poll() {
    fetch(statusUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        el("poll-error").classList.add("hidden");
        delay = 2000;
        if (!update(data)) setTimeout(poll, document.hidden ? 8000 : 3000);
      })
      .catch(function () {
        el("poll-error").classList.remove("hidden");
        delay = Math.min(delay * 2, 30000);
        setTimeout(poll, delay);
      });
  }
  poll();
})();
