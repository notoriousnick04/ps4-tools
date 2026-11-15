"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  dataUrl: null,
  previewUrl: null,
  busy: false,
  previewTimer: null,
  previewAbort: null,
};

const drop = $("drop");
const fileInput = $("file");
const preview = $("preview");
const placeholder = $("placeholder");
const fileinfo = $("fileinfo");
const statusEl = $("status");
const createBtn = $("create");
const nameInput = $("name");
const cropToggle = $("crop");
const circleToggle = $("circle");
const offlineToggle = $("offline");

const MAX_UPLOAD = 25 * 1024 * 1024;

function setStatus(text, kind = "") {
  statusEl.textContent = text;
  statusEl.className = "status" + (kind ? " " + kind : "");
}

function formatBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return Math.round(n / 1024) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

async function errorText(response) {
  try {
    const data = await response.json();
    if (data && data.error) return data.error;
  } catch (_) {
    /* not JSON */
  }
  return `${response.status} ${response.statusText}`;
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("Could not read the file"));
    reader.readAsDataURL(file);
  });
}

async function useFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    setStatus("That file is not an image.", "error");
    return;
  }
  if (file.size > MAX_UPLOAD) {
    setStatus("Image is larger than 25 MB.", "error");
    return;
  }

  try {
    state.dataUrl = await fileToDataUrl(file);
  } catch (err) {
    setStatus("Could not read the image: " + err.message, "error");
    return;
  }

  const base = (file.name || "avatar").replace(/\.[^.]+$/, "");
  nameInput.value = base || "avatar";
  fileinfo.textContent = `${file.name} · ${formatBytes(file.size)}`;
  createBtn.disabled = false;
  setStatus("");
  refreshPreview();
}

function schedulePreview() {
  clearTimeout(state.previewTimer);
  state.previewTimer = setTimeout(refreshPreview, 120);
}

async function refreshPreview() {
  if (!state.dataUrl) return;
  if (state.previewAbort) state.previewAbort.abort();
  state.previewAbort = new AbortController();

  try {
    const response = await fetch("/api/xavatar/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: state.dataUrl,
        crop: cropToggle.checked,
        circle: circleToggle.checked,
      }),
      signal: state.previewAbort.signal,
    });
    if (!response.ok) throw new Error(await errorText(response));

    const blob = await response.blob();
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(blob);
    preview.src = state.previewUrl;
    preview.hidden = false;
    placeholder.hidden = true;
    drop.classList.add("has-image");
  } catch (err) {
    if (err.name === "AbortError") return;
    setStatus("Preview failed: " + err.message, "error");
  }
}

function packageName() {
  let name = nameInput.value.trim().replace(/\.xavatar$/i, "");
  if (!name) name = "avatar";
  return name + ".xavatar";
}

async function createPackage() {
  if (!state.dataUrl || state.busy) return;

  state.busy = true;
  createBtn.disabled = true;
  createBtn.classList.add("busy");
  setStatus("Creating package…");

  try {
    const response = await fetch("/api/xavatar/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image: state.dataUrl,
        crop: cropToggle.checked,
        circle: circleToggle.checked,
        offline: offlineToggle.checked,
        filename: packageName(),
      }),
    });
    if (!response.ok) throw new Error(await errorText(response));

    const blob = await response.blob();
    const filename = packageName();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);

    setStatus(`Created ${filename} (${formatBytes(blob.size)}) — check your Downloads folder.`, "ok");
  } catch (err) {
    setStatus("Could not create the package: " + err.message, "error");
  } finally {
    state.busy = false;
    createBtn.disabled = !state.dataUrl;
    createBtn.classList.remove("busy");
  }
}

async function loadSample() {
  try {
    const response = await fetch("/xavatar/static/sample.png");
    if (!response.ok) throw new Error(await errorText(response));
    const blob = await response.blob();
    await useFile(new File([blob], "sample.png", { type: blob.type || "image/png" }));
  } catch (err) {
    setStatus("Could not load the sample image: " + err.message, "error");
  }
}

function openPicker() {
  fileInput.click();
}

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  fileInput.value = "";
  if (file) useFile(file);
});

$("browse").addEventListener("click", (event) => {
  event.stopPropagation();
  openPicker();
});

drop.addEventListener("click", openPicker);
drop.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    openPicker();
  }
});

["dragenter", "dragover"].forEach((type) => {
  drop.addEventListener(type, (event) => {
    event.preventDefault();
    drop.classList.add("drag");
  });
});

drop.addEventListener("dragleave", (event) => {
  if (!drop.contains(event.relatedTarget)) drop.classList.remove("drag");
});

drop.addEventListener("drop", (event) => {
  event.preventDefault();
  drop.classList.remove("drag");
  const file = event.dataTransfer && event.dataTransfer.files[0];
  if (file) useFile(file);
});

document.addEventListener("paste", (event) => {
  const items = event.clipboardData ? Array.from(event.clipboardData.items) : [];
  const item = items.find((entry) => entry.type.startsWith("image/"));
  if (item) {
    const file = item.getAsFile();
    if (file) useFile(file);
  }
});

cropToggle.addEventListener("change", schedulePreview);
circleToggle.addEventListener("change", schedulePreview);
createBtn.addEventListener("click", createPackage);
$("sample").addEventListener("click", loadSample);

nameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") createPackage();
});

if (new URLSearchParams(location.search).has("sample")) {
  loadSample();
}
