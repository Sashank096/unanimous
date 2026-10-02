(function () {
  const experienceList = document.getElementById("experienceList");
  const educationList = document.getElementById("educationList");
  const projectsList = document.getElementById("projectsList");
  const skillsChips = document.getElementById("skillsChips");
  const skillInput = document.getElementById("skillInput");
  const preview = document.getElementById("resumePreview");
  const templateSelect = document.getElementById("templateSelect");
  const fontSelect = document.getElementById("fontSelect");
  const accentInput = document.getElementById("accentInput");
  const swatches = document.getElementById("swatches");
  const form = document.getElementById("builderForm");

  function esc(s) {
    return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function entryBlockHTML(fields) {
    if (fields.type === "experience") {
      return `<div class="entry-block">
        <button type="button" class="rm">×</button>
        <div class="form-row"><div class="field"><label>Title</label><input type="text" class="f-title"></div><div class="field"><label>Organisation</label><input type="text" class="f-org"></div></div>
        <div class="form-row"><div class="field"><label>Start</label><input type="text" class="f-start"></div><div class="field"><label>End</label><input type="text" class="f-end"></div></div>
        <div class="field"><label style="display:flex;justify-content:space-between;align-items:center">Description <button type="button" class="ai-btn" data-ai-desc="1">✦ Enhance</button></label><textarea class="f-desc"></textarea></div>
      </div>`;
    }
    if (fields.type === "education") {
      return `<div class="entry-block">
        <button type="button" class="rm">×</button>
        <div class="form-row"><div class="field"><label>Degree</label><input type="text" class="f-degree"></div><div class="field"><label>School</label><input type="text" class="f-school"></div></div>
        <div class="form-row"><div class="field"><label>Start</label><input type="text" class="f-start"></div><div class="field"><label>End</label><input type="text" class="f-end"></div></div>
        <div class="field"><label>Notes</label><textarea class="f-desc"></textarea></div>
      </div>`;
    }
    return `<div class="entry-block">
      <button type="button" class="rm">×</button>
      <div class="form-row"><div class="field"><label>Name</label><input type="text" class="f-name"></div><div class="field"><label>Link</label><input type="text" class="f-link" placeholder="https://..."></div></div>
      <div class="field"><label>Project image <span class="upload-status"></span></label><input type="file" class="f-image" accept="image/png,image/jpeg,image/webp"><input type="text" class="f-image-url" placeholder="Or paste an image URL"></div>
      <div class="field"><label style="display:flex;justify-content:space-between;align-items:center">Description <button type="button" class="ai-btn" data-ai-desc="1">✦ Enhance</button></label><textarea class="f-desc"></textarea></div>
    </div>`;
  }

  document.getElementById("addExperience").addEventListener("click", () => {
    experienceList.insertAdjacentHTML("beforeend", entryBlockHTML({ type: "experience" }));
    renderPreview();
  });
  document.getElementById("addEducation").addEventListener("click", () => {
    educationList.insertAdjacentHTML("beforeend", entryBlockHTML({ type: "education" }));
    renderPreview();
  });
  document.getElementById("addProject").addEventListener("click", () => {
    projectsList.insertAdjacentHTML("beforeend", entryBlockHTML({ type: "project" }));
    renderPreview();
  });

  document.querySelectorAll(".b-section").forEach((section) => {
    section.addEventListener("click", (e) => {
      if (e.target.classList.contains("rm")) {
        e.target.closest(".entry-block").remove();
        renderPreview();
      }
    });
  });

  function addSkill() {
    const val = skillInput.value.trim();
    if (!val) return;
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.dataset.skill = val;
    chip.innerHTML = `${esc(val)}<button type="button" class="rm-chip">×</button>`;
    skillsChips.appendChild(chip);
    skillInput.value = "";
    renderPreview();
  }
  document.getElementById("addSkill").addEventListener("click", addSkill);
  skillInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addSkill(); } });
  skillsChips.addEventListener("click", (e) => {
    if (e.target.classList.contains("rm-chip")) {
      e.target.closest(".chip").remove();
      renderPreview();
    }
  });

  document.addEventListener("change", async (e) => {
    if (!e.target.classList.contains("f-image") || !e.target.files[0]) return;
    const input = e.target;
    const block = input.closest(".entry-block");
    const status = block.querySelector(".upload-status");
    const formData = new FormData();
    formData.append("image", input.files[0]);
    status.textContent = "Uploading…";
    try {
      const response = await fetch("/api/project-image", { method: "POST", body: formData });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Upload failed.");
      block.querySelector(".f-image-url").value = data.url;
      status.textContent = "Uploaded";
      renderPreview();
    } catch (error) {
      status.textContent = error.message;
    }
  });

  // AI enhance — calls the Flask backend, which calls Gemini server-side
  // (the API key never touches the browser).
  document.addEventListener("click", async (e) => {
    if (!e.target.classList.contains("ai-btn")) return;
    const btn = e.target;
    let textarea, kind;
    if (btn.dataset.aiTarget) {
      textarea = document.getElementById(btn.dataset.aiTarget);
      kind = "summary";
    } else {
      textarea = btn.closest(".field").querySelector("textarea.f-desc");
      kind = "bullet";
    }
    if (!textarea || !textarea.value.trim()) {
      showToast("Write a draft first, then enhance it ✦");
      return;
    }
    const original = btn.textContent;
    btn.textContent = "Thinking…";
    btn.disabled = true;
    try {
      const res = await fetch("/api/enhance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: textarea.value, kind }),
      });
      const data = await res.json();
      if (data.ok) {
        textarea.value = data.text;
        renderPreview();
        showToast(data.source === "local" ? "Polished locally ✦" : "Enhanced with AI ✦");
      } else {
        showToast(data.error || "Couldn't enhance that — try again.");
      }
    } catch (err) {
      showToast("Network error — check your connection.");
    } finally {
      btn.textContent = original;
      btn.disabled = false;
    }
  });

  function showToast(msg) {
    let toast = document.querySelector(".toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "toast";
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function collectContent() {
    const experience = Array.from(experienceList.querySelectorAll(".entry-block")).map((el) => ({
      title: el.querySelector(".f-title").value,
      org: el.querySelector(".f-org").value,
      start: el.querySelector(".f-start").value,
      end: el.querySelector(".f-end").value,
      desc: el.querySelector(".f-desc").value,
    }));
    const education = Array.from(educationList.querySelectorAll(".entry-block")).map((el) => ({
      degree: el.querySelector(".f-degree").value,
      school: el.querySelector(".f-school").value,
      start: el.querySelector(".f-start").value,
      end: el.querySelector(".f-end").value,
      desc: el.querySelector(".f-desc").value,
    }));
    const projects = Array.from(projectsList.querySelectorAll(".entry-block")).map((el) => ({
      name: el.querySelector(".f-name").value,
      link: el.querySelector(".f-link").value,
      image: el.querySelector(".f-image-url").value,
      desc: el.querySelector(".f-desc").value,
    }));
    const skills = Array.from(skillsChips.querySelectorAll(".chip")).map((c) => c.dataset.skill);
    return {
      headline: document.getElementById("headlineField").value,
      summary: document.getElementById("summaryField").value,
      experience, education, projects, skills,
    };
  }

  function displayLink(v) {
    v = (v || "").trim();
    v = v.replace(/^https?:\/\//, "");
    v = v.replace(/^www\./, "");
    return v.replace(/\/$/, "");
  }

  function renderItem(top, sub, dateStr, desc) {
    return `<div class="r-item">
      <div class="r-item-top"><span>${esc(top)}</span><span class="r-item-date">${esc(dateStr)}</span></div>
      ${sub ? `<div class="r-item-org">${esc(sub)}</div>` : ""}
      ${desc ? `<p>${esc(desc)}</p>` : ""}
    </div>`;
  }

  function renderPreview() {
    const content = collectContent();
    const base = window.UNANI_RESUME_BASE;
    const tpl = templateSelect.value;
    const font = fontSelect.value;
    const accent = accentInput.value;

    const contactHTML = base.contact.filter(Boolean).map((c) => `<span>${esc(displayLink(c))}</span>`).join("");
    const headerTop = base.photo
      ? `<div class="r-photo-row"><img class="r-photo" src="${esc(base.photo)}" alt=""><div><div class="r-name">${esc(base.name)}</div>${content.headline ? `<div class="r-headline">${esc(content.headline)}</div>` : ""}</div></div>`
      : `<div class="r-name">${esc(base.name)}</div>${content.headline ? `<div class="r-headline">${esc(content.headline)}</div>` : ""}`;

    const expHTML = content.experience.length
      ? `<div class="r-experience"><h5>Experience</h5>${content.experience.map((e) => renderItem(e.title, e.org, [e.start, e.end].filter(Boolean).join(" – "), e.desc)).join("")}</div>`
      : "";
    const eduHTML = content.education.length
      ? `<div class="r-education"><h5>Education</h5>${content.education.map((e) => renderItem(e.degree || e.school, e.degree && e.school ? e.school : "", [e.start, e.end].filter(Boolean).join(" – "), e.desc)).join("")}</div>`
      : "";
    const projHTML = content.projects.length
      ? `<div class="r-projects"><h5>Projects</h5>${content.projects.map((p) => renderItem(p.name, "", p.link, p.desc)).join("")}</div>`
      : "";
    const skillsHTML = content.skills.length
      ? `<div class="r-skills"><h5>Skills</h5><div class="r-skill-chips">${content.skills.map((s) => `<span>${esc(s)}</span>`).join("")}</div></div>`
      : "";
    const summaryHTML = content.summary ? `<div class="r-summary"><h5>Summary</h5><p>${esc(content.summary)}</p></div>` : "";

    preview.innerHTML = `<div class="resume-doc rt-${tpl}" style="--r-font:'${font}',Arial,sans-serif;--r-accent:${accent}">
      <div class="r-header">
        ${headerTop}
        <div class="r-contact">${contactHTML}</div>
      </div>
      ${summaryHTML}${expHTML}${eduHTML}${projHTML}${skillsHTML}
    </div>`;
  }

  templateSelect.addEventListener("change", renderPreview);
  fontSelect.addEventListener("change", renderPreview);
  swatches.addEventListener("click", (e) => {
    if (e.target.classList.contains("swatch")) {
      accentInput.value = e.target.dataset.color;
      swatches.querySelectorAll(".swatch").forEach((s) => s.classList.remove("active"));
      e.target.classList.add("active");
      renderPreview();
    }
  });
  document.addEventListener("input", (e) => {
    if (e.target.closest(".builder-panel")) renderPreview();
  });

  document.getElementById("downloadBtn").addEventListener("click", () => window.print());

  form.addEventListener("submit", () => {
    document.getElementById("contentJson").value = JSON.stringify(collectContent());
  });

  renderPreview();
})();
