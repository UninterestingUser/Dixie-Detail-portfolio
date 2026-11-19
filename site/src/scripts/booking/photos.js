// Photos for a quote request (public-api.md, quote requests): optional, up
// to the API's limit. The first photo picked opens an upload session after
// a Turnstile check; each photo then uploads on its own as soon as it is
// picked, so one slow photo never loses the form. Each shows a thumbnail, a
// remove button and its upload progress. When the browser can read a photo
// it is shrunk before sending (at most 2560 pixels on its long side, as a
// JPEG); one it can't read, such as HEIC on most browsers, goes as it is.
// The server checks and cleans every photo either way.

import { apiUrl, del, post } from "./api.js";
import { h } from "./dom.js";
import { token } from "./turnstile.js";

const LONG_SIDE = 2560;

async function shrink(file) {
  if (!window.createImageBitmap) return file;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  const scale = Math.min(1, LONG_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  if (!blob || (scale === 1 && blob.size >= file.size)) return file;
  return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
}

function send(session, file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("photo", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", apiUrl(`quote-requests/uploads/${session}/photos`));
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total); // not money: upload progress
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { body = {}; }
      if (xhr.status === 201) resolve(body);
      else reject(new Error(body.message || "That photo didn't upload."));
    };
    // Generous, for a large photo on a slow phone connection, but never endless.
    xhr.timeout = 180000;
    xhr.onerror = () => reject(new Error("That photo didn't upload. Check the connection and add it again."));
    xhr.ontimeout = () => reject(new Error("That photo took too long to upload. Check the connection and add it again."));
    xhr.send(form);
  });
}

export function photoPicker({ config, limits, box }) {
  const max = limits.max_per_request;
  const maxBytes = limits.max_megabytes * 1024 * 1024;
  const photos = [];
  let session = null;
  let opening = null;
  const grid = h("div", { class: "photos", "aria-live": "polite" });
  const message = h("p", { class: "error", role: "alert" });
  const input = h("input", { type: "file", id: "qr-photos", accept: limits.types.join(",") + ",image/*", multiple: true, class: "visually-hidden" });
  const add = h("label", { for: "qr-photos", class: "button outline" }, "Add photos");
  const element = h("div", { class: "stack", style: "gap:10px" },
    h("p", { class: "label", style: "margin:0" }, "Photos"),
    h("p", { class: "hint", style: "margin:0" }, `Photos are optional, but helpful in providing an accurate estimate. Add up to ${max} photos.`),
    grid, h("div", {}, input, add), message);

  const openSession = () => {
    opening ||= token(config, box)
      .then((value) => post("quote-requests/uploads", { turnstile: value }))
      .then(({ body }) => (session = body.session))
      .catch((error) => { opening = null; throw error; });
    return opening;
  };

  function tile(photo) {
    const bar = h("progress", { max: "1", value: "0", "aria-label": `Uploading ${photo.file.name}` });
    const state = h("span", { class: "state" }, "Waiting");
    const remove = h("button", { type: "button", class: "remove", "aria-label": `Remove ${photo.file.name}`, onclick: () => drop(photo) }, "×");
    const thumb = photo.preview ? h("img", { src: photo.preview, alt: "" }) : h("span", { class: "hint" }, photo.file.name);
    photo.el = h("div", { class: "photo-tile" }, thumb, bar, state, remove);
    photo.bar = bar;
    photo.state = state;
    return photo.el;
  }

  async function drop(photo) {
    photos.splice(photos.indexOf(photo), 1);
    photo.el.remove();
    if (photo.preview) URL.revokeObjectURL(photo.preview);
    if (photo.id && session) del(`quote-requests/uploads/${session}/photos/${photo.id}`).catch(() => {});
  }

  async function upload(photo) {
    try {
      const file = await shrink(photo.file);
      if (file.size > maxBytes) throw new Error(`That photo is over ${limits.max_megabytes} MB. Pick a smaller one.`);
      if (file !== photo.file && file.type === "image/jpeg") {
        if (photo.preview) URL.revokeObjectURL(photo.preview);
        photo.preview = URL.createObjectURL(file);
        photo.el.querySelector("img")?.setAttribute("src", photo.preview);
      }
      photo.state.textContent = "Uploading";
      await openSession();
      const answer = await send(session, file, (part) => (photo.bar.value = part));
      photo.id = answer.photo;
      photo.bar.remove();
      photo.state.textContent = "Added";
    } catch (error) {
      photo.failed = true;
      photo.state.textContent = "Not added";
      message.textContent = error.message;
    }
  }

  input.addEventListener("change", () => {
    message.textContent = "";
    for (const file of input.files) {
      if (photos.length >= max) {
        message.textContent = `A request can have up to ${max} photos.`;
        break;
      }
      const preview = /^image\/(jpeg|png|webp|gif)$/.test(file.type) ? URL.createObjectURL(file) : null;
      const photo = { file, preview, id: null };
      photos.push(photo);
      grid.append(tile(photo));
      photo.done = upload(photo);
    }
    input.value = "";
  });

  return {
    element,
    async ready() {
      await Promise.all(photos.map((photo) => photo.done));
      return { session, photos: photos.filter((photo) => photo.id).map((photo) => photo.id) };
    },
    count: () => photos.length,
  };
}
