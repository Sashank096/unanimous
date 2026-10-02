// Animated title letters (hero only — safe no-op elsewhere)
const title = document.getElementById("title");
if (title) {
  "U_NANI_MOUS".split("").forEach((ch, i) => {
    const s = document.createElement("span");
    s.className = "letter";
    s.style.setProperty("--i", i);
    s.textContent = ch === " " ? "\u00a0" : ch;
    title.appendChild(s);
  });
}

// Theme toggle — the theme itself is already applied by the inline script
// in base.html <head> (before paint, to avoid a flash of wrong colors).
// This just wires up the button and keeps its icon in sync.
const root = document.documentElement;
const theme = document.getElementById("theme");
const saved = root.dataset.theme || "dark";
if (theme) {
  theme.textContent = saved === "light" ? "☀" : "☾";
  theme.onclick = () => {
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    localStorage.setItem("unani-theme", next);
    theme.textContent = next === "light" ? "☀" : "☾";
  };
}

// Scroll-reveal for the idea section
const introEl = document.querySelector(".intro");
if (introEl) {
  const observer = new IntersectionObserver(
    (entries) => entries.forEach((e) => { if (e.isIntersecting) e.target.classList.add("show"); }),
    { threshold: 0.2 }
  );
  observer.observe(introEl);
}

// Mobile hamburger menu
const hamburger = document.getElementById("hamburger");
const mobileMenu = document.getElementById("mobileMenu");
if (hamburger && mobileMenu) {
  hamburger.addEventListener("click", () => {
    const open = mobileMenu.classList.toggle("open");
    hamburger.setAttribute("aria-expanded", open ? "true" : "false");
  });
  mobileMenu.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", () => {
      mobileMenu.classList.remove("open");
      hamburger.setAttribute("aria-expanded", "false");
    });
  });
}
