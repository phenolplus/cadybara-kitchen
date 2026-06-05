const STORAGE_KEY = "cadybara-local-accounts";
const SESSION_KEY = "cadybara-local-session";

const dom = {
  startNow: document.querySelector("#start-now"),
  register: document.querySelector("#register"),
  dialog: document.querySelector("#auth-dialog"),
  form: document.querySelector("#auth-form"),
  close: document.querySelector("#auth-close"),
  kicker: document.querySelector("#auth-kicker"),
  title: document.querySelector("#auth-title"),
  name: document.querySelector("#auth-name"),
  email: document.querySelector("#auth-email"),
  password: document.querySelector("#auth-password"),
  message: document.querySelector("#auth-message"),
  submit: document.querySelector("#auth-submit"),
  swap: document.querySelector("#auth-swap"),
};

let authMode = "signin";
const DASHBOARD_URL = "./dashboard.html";

function readAccounts() {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeAccounts(accounts) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(accounts));
}

function readSession() {
  try {
    return JSON.parse(window.localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function writeSession(session) {
  if (session) {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } else {
    window.localStorage.removeItem(SESSION_KEY);
  }
}

async function hashPassword(password) {
  if (!window.crypto?.subtle) {
    return `demo-${password}`;
  }
  const bytes = new TextEncoder().encode(password);
  const digest = await window.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function setMessage(text = "", isError = false) {
  dom.message.textContent = text;
  dom.message.classList.toggle("error", isError);
}

function setMode(mode) {
  authMode = mode;
  dom.form.dataset.mode = mode;
  dom.name.required = mode === "register";
  dom.password.autocomplete = mode === "register" ? "new-password" : "current-password";
  dom.kicker.textContent = mode === "register" ? "Register" : "Start now";
  dom.title.textContent = mode === "register" ? "Create account" : "Sign in";
  dom.submit.textContent = mode === "register" ? "Create account" : "Sign in";
  dom.swap.textContent = mode === "register" ? "Already have an account? Sign in" : "Need an account? Register";
  setMessage();
}

function openAuth(mode) {
  setMode(mode);
  dom.form.reset();
  if (typeof dom.dialog.showModal === "function" && !dom.dialog.open) {
    dom.dialog.showModal();
  } else {
    dom.dialog.setAttribute("open", "");
  }
  window.setTimeout(() => {
    const firstField = mode === "register" ? dom.name : dom.email;
    firstField.focus();
  }, 0);
}

function openSignedInState() {
  setMode("signin");
  dom.form.reset();
  dom.kicker.textContent = "Ready";
  dom.title.textContent = "You're signed in";
  dom.submit.textContent = "Close";
  dom.swap.textContent = "Sign out";
  setMessage("Demo mode is ready. The landing page is intentionally the whole experience right now.");
  if (typeof dom.dialog.showModal === "function" && !dom.dialog.open) {
    dom.dialog.showModal();
  } else {
    dom.dialog.setAttribute("open", "");
  }
}

function closeAuth() {
  if (typeof dom.dialog.close === "function") {
    dom.dialog.close();
  } else {
    dom.dialog.removeAttribute("open");
  }
}

function openDashboard() {
  window.location.href = DASHBOARD_URL;
}

function updateNav() {
  const session = readSession();
  if (!session) {
    dom.startNow.textContent = "Start now";
    dom.register.textContent = "Register";
    return;
  }

  dom.startNow.textContent = "Open app";
  dom.register.textContent = "Sign out";
}

async function registerAccount(formData) {
  const name = formData.get("name").trim() || "Demo Builder";
  const email = formData.get("email").trim().toLowerCase() || "demo@cadybara.local";
  const password = formData.get("password") || "demo-password";
  const accounts = readAccounts();
  const existing = accounts.find((account) => account.email === email);

  if (existing) {
    writeSession({ name: existing.name, email: existing.email });
    updateNav();
    closeAuth();
    openDashboard();
    return;
  }

  const passwordHash = await hashPassword(password);
  accounts.push({ name, email, passwordHash });
  writeAccounts(accounts);
  writeSession({ name, email });
  updateNav();
  closeAuth();
  openDashboard();
}

async function signIn(formData) {
  const email = formData.get("email").trim().toLowerCase() || "demo@cadybara.local";
  const password = formData.get("password") || "demo-password";
  const passwordHash = await hashPassword(password);
  const accounts = readAccounts();
  let account = accounts.find((item) => item.email === email && item.passwordHash === passwordHash);

  if (!account) {
    account = { name: "Demo Builder", email, passwordHash };
    accounts.push(account);
    writeAccounts(accounts);
  }

  writeSession({ name: account.name, email: account.email });
  updateNav();
  closeAuth();
  openDashboard();
}

dom.startNow.addEventListener("click", () => {
  if (readSession()) {
    openDashboard();
    return;
  }
  openAuth("signin");
});

dom.register.addEventListener("click", () => {
  if (readSession()) {
    writeSession(null);
    updateNav();
    return;
  }
  openAuth("register");
});

dom.close.addEventListener("click", closeAuth);

dom.swap.addEventListener("click", () => {
  if (readSession() && dom.title.textContent === "You're signed in") {
    writeSession(null);
    updateNav();
    closeAuth();
    return;
  }
  setMode(authMode === "register" ? "signin" : "register");
});

dom.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (readSession() && dom.title.textContent === "You're signed in") {
    closeAuth();
    return;
  }
  const formData = new FormData(dom.form);
  if (authMode === "register") {
    await registerAccount(formData);
  } else {
    await signIn(formData);
  }
});

dom.dialog.addEventListener("click", (event) => {
  if (event.target === dom.dialog) {
    closeAuth();
  }
});

updateNav();
