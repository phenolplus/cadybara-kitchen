const SESSION_KEY = "cadybara-local-session";

const dom = {
  projects: document.querySelectorAll(".project-card"),
  newProject: document.querySelector("#new-project"),
  logout: document.querySelector("#logout"),
  focusArt: document.querySelector("#focus-art"),
  focusKicker: document.querySelector("#focus-kicker"),
  focusTitle: document.querySelector("#focus-title"),
  focusSummary: document.querySelector("#focus-summary"),
  focusFocus: document.querySelector("#focus-focus"),
  focusUse: document.querySelector("#focus-use"),
  focusSurface: document.querySelector("#focus-surface"),
};

function clearSelection() {
  dom.projects.forEach((project) => {
    project.classList.remove("is-selected");
    project.setAttribute("aria-pressed", "false");
  });
}

function setText(element, value) {
  if (!element) return;
  element.textContent = value || "";
}

function selectProject(project, { scroll = false } = {}) {
  if (!project) return;
  clearSelection();
  project.classList.add("is-selected");
  project.setAttribute("aria-pressed", "true");

  const { kicker, title, summary, focus, use, surface, stone } = project.dataset;
  dom.focusArt.className = `focus-art ${stone || "stone-1"}`;
  setText(dom.focusKicker, kicker);
  setText(dom.focusTitle, title);
  setText(dom.focusSummary, summary);
  setText(dom.focusFocus, focus);
  setText(dom.focusUse, use);
  setText(dom.focusSurface, surface);

  if (scroll) {
    project.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

dom.projects.forEach((project) => {
  project.addEventListener("click", () => selectProject(project));
});

dom.newProject.addEventListener("click", () => {
  selectProject(document.querySelector('[data-project="new"]'), { scroll: true });
});

dom.logout.addEventListener("click", () => {
  window.localStorage.removeItem(SESSION_KEY);
  window.location.href = "./";
});

selectProject(document.querySelector(".project-card.is-selected") || dom.projects[0]);
