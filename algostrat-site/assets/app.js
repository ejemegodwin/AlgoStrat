/* AlgoStrat site interactivity
 * Plain vanilla JS — no frameworks, no build step.
 * Defer-loaded so it runs after DOM is parsed.
 */

// ── Centralized copy ──────────────────────────────────────────────
const COPY = {
  nav: {
    howItWorks: "How it works",
    forWorkers: "For workers",
    faqs: "FAQ",
  },
  hero: {
    headline: "Make your work speak for itself.",
    subhead: "Complete real tasks, build a portable record, and prove your capability across borders.",
    ctaPrimary: "Join the waitlist",
    ctaSecondary: "See a sample receipt",
  },
  tabs: {
    workers: "For workers",
    businesses: "For businesses",
  },
  receipt: {
    title: "Try the receipt",
    subhead: "Verify a receipt's integrity in your browser.",
    verify: "Verify",
    edit: "Edit a detail",
    verified: "Verified",
    tampered: "Tampered",
    notSupported:
      "Your browser cannot run Web Crypto verification. This demo requires a modern browser.",
    disclosure:
      "Demo of the idea. Real receipts are signed and verified by AlgoStrat's server.",
    mismatch:
      "The hash no longer matches the original — the data has been modified since the receipt was issued.",
    valid:
      "The hash matches the original expected digest. This sample data is intact.",
    editPrompt: "Edit the task title below, then click Verify to see how tampering is detected.",
  },
  waitlist: {
    heading: "Join the waitlist",
    subhead: "Be the first to know when tasks are available.",
    emailLabel: "Email address",
    emailPlaceholder: "you@example.com",
    consentLabel: "I consent to being contacted about AlgoStrat. You can unsubscribe at any time.",
    submit: "Join the waitlist",
    submitting: "Submitting…",
    success: "Thanks — we'll be in touch!",
    consentError: "You must consent to being contacted.",
    audienceError: "Please select an audience.",
    emailError: "Please enter a valid email address.",
    genericError: "Something went wrong. Please try again.",
    duplicateError: "That email is already on the waitlist.",
    networkError: "Network error — check your connection and try again.",
  },
};

// ── DOM ready helper ──────────────────────────────────────────────
function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
  } else {
    callback();
  }
}

onReady(() => {
  initTheme();
  initMobileMenu();
  initTabs();
  initReceipt();
  initWaitlist();
  document.body.classList.remove("no-js");
});

// ── Theme management ──────────────────────────────────────────────
function getStoredTheme() {
  try {
    return localStorage.getItem("theme");
  } catch (e) {
    return null;
  }
}

function setStoredTheme(theme) {
  try {
    localStorage.setItem("theme", theme);
  } catch (e) {
    // Storage unavailable — theme just won't persist
  }
}

function initTheme() {
  const root = document.documentElement;
  const stored = getStoredTheme();

  if (!stored) {
    // Respect system preference on first visit
    const prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.setAttribute("data-theme", prefersDark ? "dark" : "light");
  } else {
    root.setAttribute("data-theme", stored);
  }

  updateThemeToggle();

  // Watch for system preference changes if no explicit choice saved
  if (!stored && window.matchMedia) {
    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", (e) => {
        if (!getStoredTheme()) {
          root.setAttribute(
            "data-theme",
            e.matches ? "dark" : "light"
          );
          updateThemeToggle();
        }
      });
  }

  const toggles = document.querySelectorAll("#themeToggle, #themeToggleFooter");
  toggles.forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      setStoredTheme(next);
      updateThemeToggle();
    });
  });
}

function updateThemeToggle() {
  const root = document.documentElement;
  const isLight = root.getAttribute("data-theme") === "light";
  const toggles = document.querySelectorAll("#themeToggle, #themeToggleFooter");
  toggles.forEach((t) => (t.textContent = isLight ? "☀️" : "🌙"));
}

// ── Mobile menu ───────────────────────────────────────────────────
function initMobileMenu() {
  const btn = document.getElementById("mobileMenuBtn");
  const panel = document.getElementById("mobileMenuPanel");
  if (!btn || !panel) return;

  const closePanel = () => {
    btn.setAttribute("aria-expanded", "false");
    panel.style.display = "none";
  };

  const openPanel = () => {
    btn.setAttribute("aria-expanded", "true");
    panel.style.display = "block";
  };

  // Toggle on click — but only show on mobile
  const isMobile = () => window.innerWidth <= 768;
  const toggle = () => {
    if (btn.getAttribute("aria-expanded") === "true") {
      closePanel();
    } else {
      openPanel();
    }
  };

  // Show toggle button only on mobile
  const updateVisibility = () => {
    if (isMobile()) {
      btn.style.display = "block";
    } else {
      closePanel();
    }
  };
  updateVisibility();
  window.addEventListener("resize", updateVisibility);
  btn.addEventListener("click", toggle);

  // Close on Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && btn.getAttribute("aria-expanded") === "true") {
      closePanel();
      btn.focus();
    }
  });

  // Close on link click
  panel.addEventListener("click", (e) => {
    if (e.target.tagName === "A") {
      closePanel();
    }
  });

  // Click-away to close
  document.addEventListener("click", (e) => {
    if (btn.getAttribute("aria-expanded") === "true" && !panel.contains(e.target) && e.target !== btn) {
      closePanel();
    }
  });
}

// ── Tabs ──────────────────────────────────────────────────────────
function initTabs() {
  const tabList = document.querySelector('[role="tablist"]');
  if (!tabList) return;

  const tabs = tabList.querySelectorAll('[role="tab"]');

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const selected = tab.getAttribute("aria-selected") === "true";
      if (selected) return;

      // Update tabs
      tabs.forEach((t) => {
        t.setAttribute("aria-selected", "false");
      });
      tab.setAttribute("aria-selected", "true");

      // Update panels
      const panels = document.querySelectorAll('[role="tabpanel"]');
      panels.forEach((panel) => {
        const tabId = tab.getAttribute("id");
        if (panel.getAttribute("id") === tab.getAttribute("aria-controls")) {
          panel.removeAttribute("hidden");
        } else {
          panel.setAttribute("hidden", "");
        }
      });
    });

    // Keyboard navigation
    tab.addEventListener("keydown", (e) => {
      const currentIndex = Array.from(tabs).indexOf(tab);
      let nextTab = null;

      switch (e.key) {
        case "ArrowRight":
        case "ArrowDown":
          nextTab = tabs[(currentIndex + 1) % tabs.length];
          nextTab?.focus();
          nextTab?.click();
          e.preventDefault();
          break;
        case "ArrowLeft":
        case "ArrowUp":
          nextTab = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
          nextTab?.focus();
          nextTab?.click();
          e.preventDefault();
          break;
        case "Home":
          tabs[0]?.focus();
          tabs[0]?.click();
          e.preventDefault();
          break;
        case "End":
          tabs[tabs.length - 1]?.focus();
          tabs[tabs.length - 1]?.click();
          e.preventDefault();
          break;
      }
    });
  });

  // CTA buttons scroll to their targets
  const scrollTo = (btnId, targetId) => {
    const b = document.getElementById(btnId);
    if (!b) return;
    b.addEventListener("click", (e) => {
      e.preventDefault();
      const target = document.getElementById(targetId);
      if (target) {
        const top = target.getBoundingClientRect().top + window.pageYOffset - 80;
        window.scrollTo({ top, behavior: "smooth" });
      }
    });
  };
  scrollTo("waitlistBtn", "waitlist");
  scrollTo("heroWaitlistBtn", "waitlist");
  scrollTo("heroReceiptBtn", "receipt-section");
}

// ── Receipt verification ──────────────────────────────────────────
const SAMPLE_RECEIPT = {
  taskId: "Build a responsive nav bar",
  receiptId: "A7F3-B9E2",
  criteriaMet: "5/5",
  date: "Oct 28, 2026",
};

const ORIGINAL_JSON = JSON.stringify({
  taskId: SAMPLE_RECEIPT.taskId,
  receiptId: SAMPLE_RECEIPT.receiptId,
  criteriaMet: SAMPLE_RECEIPT.criteriaMet,
  date: SAMPLE_RECEIPT.date,
});

let ORIGINAL_HASH = null;
let EDIT_MODE = false;

async function sha256(text) {
  const data = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

function truncateHash(hash) {
  if (!hash) return "";
  return hash.slice(0, 16) + "…" + hash.slice(-4);
}

async function computeAndDisplayHash() {
  const currentJson = JSON.stringify({
    taskId: document.getElementById("receiptTask").textContent,
    receiptId: document.getElementById("receiptId").textContent.replace("#", ""),
    criteriaMet: "5/5",
    date: document.getElementById("receiptDate").textContent,
  });

  try {
    const hash = await sha256(currentJson);
    document.getElementById("receiptDisplayHash").textContent = truncateHash(hash);
    return hash;
  } catch (e) {
    return null;
  }
}

async function computeOriginalHash() {
  ORIGINAL_HASH = await sha256(ORIGINAL_JSON);
  document.getElementById("receiptDisplayHash").textContent = truncateHash(ORIGINAL_HASH);
}

function initReceipt() {
  const verifyBtn = document.getElementById("verifyBtn");
  if (!window.crypto || !crypto.subtle || !crypto.subtle.digest) {
    if (verifyBtn) {
      verifyBtn.disabled = true;
      verifyBtn.textContent = "Web Crypto unavailable";
    }
    return;
  }

  computeOriginalHash();

  const editBtn = document.getElementById("editBtn");
  const taskEl = document.getElementById("receiptTask");
  const statusBadge = document.getElementById("receiptStatusBadge");
  const disclosure = document.querySelector("#receipt-section .ink-muted:last-of-type") ||
    document.querySelector("#receipt-section p:last-child");

  if (verifyBtn) {
    verifyBtn.addEventListener("click", async () => {
      const currentFull = await sha256(
        JSON.stringify({
          taskId: taskEl.textContent,
          receiptId: document.getElementById("receiptId").textContent.replace("#", ""),
          criteriaMet: "5/5",
          date: document.getElementById("receiptDate").textContent,
        })
      );

      await computeAndDisplayHash();

      if (!currentFull || !ORIGINAL_HASH) {
        alert(COPY.receipt.notSupported);
        return;
      }

      if (currentFull === ORIGINAL_HASH) {
        statusBadge.textContent = COPY.receipt.verified;
        statusBadge.className = "badge badge-verified";
        alert(COPY.receipt.valid);
      } else {
        statusBadge.textContent = COPY.receipt.tampered;
        statusBadge.className = "badge badge-notyet";
        alert(COPY.receipt.mismatch);
      }
    });
  }

  if (editBtn) {
    editBtn.addEventListener("click", () => {
      if (EDIT_MODE) {
        // Save
        taskEl.contentEditable = "false";
        EDIT_MODE = false;
        editBtn.textContent = COPY.receipt.edit;
      } else {
        taskEl.contentEditable = "true";
        taskEl.focus();
        // Select text
        const range = document.createRange();
        range.selectNodeContents(taskEl);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        EDIT_MODE = true;
        editBtn.textContent = "Done editing";
      }
    });
  }

  // Show disclosure in both hero and section
  const disclosures = document.querySelectorAll("#receipt-section .ink-muted");
  if (disclosure && disclosures.length > 0) {
    const lastDisclosure = disclosures[disclosures.length - 1];
    if (lastDisclosure) {
      lastDisclosure.textContent = COPY.receipt.disclosure;
    }
  }
}

// ── Waitlist form ─────────────────────────────────────────────────
function initWaitlist() {
  const form = document.getElementById("waitlistForm");
  if (!form) return;

  const emailInput = document.getElementById("waitlistEmail");
  const submitText = document.getElementById("submitText");
  const spinner = document.getElementById("submitSpinner");
  const submitBtn = document.getElementById("submitBtn");

  let isSubmitting = false;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    // Reset errors
    document.getElementById("emailError").style.display = "none";
    document.getElementById("audienceError").style.display = "none";
    document.getElementById("consentError").style.display = "none";

    const email = emailInput.value.trim();
    const audience = form.elements["audience"]?.value;
    const region = form.elements["region"]?.value || "";
    const consent = form.elements["consent"]?.checked;

    // Validation
    let hasError = false;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email || !emailRegex.test(email)) {
      document.getElementById("emailError").textContent = COPY.waitlist.emailError;
      document.getElementById("emailError").style.display = "block";
      hasError = true;
    }
    if (!audience) {
      document.getElementById("audienceError").textContent = COPY.waitlist.audienceError;
      document.getElementById("audienceError").style.display = "block";
      hasError = true;
    }
    if (!consent) {
      document.getElementById("consentError").textContent = COPY.waitlist.consentError;
      document.getElementById("consentError").style.display = "block";
      hasError = true;
    }

    if (hasError) return;

    // Submit
    isSubmitting = true;
    submitText.textContent = COPY.waitlist.submitting;
    spinner.style.display = "inline-block";

    const apiBase = form.getAttribute("data-api-base") || "/waitlist";

    try {
      const response = await fetch(apiBase, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, audience, region, consent: true }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json().catch(() => ({}));

      // Success
      form.innerHTML = `
        <div class="flex-center" style="gap: var(--space-sm); flex-direction: column; text-align: center;">
          <div style="font-size: 1.5rem;">✓</div>
          <h3 class="h4">${COPY.waitlist.success}</h3>
          <p class="ink-muted" id="waitlistDone"></p>
        </div>
      `;
      document.getElementById("waitlistDone").textContent = email;
    } catch (error) {
      // Failure — show error state
      submitText.textContent = COPY.waitlist.submit;
      spinner.style.display = "none";
      isSubmitting = false;

      const msg = error.message.includes("HTTP 409")
        ? COPY.waitlist.duplicateError
        : error.message === "Failed to fetch" || error.message.includes("HTTP 0")
          ? COPY.waitlist.networkError
          : COPY.waitlist.genericError;
      alert(msg);
    }
  });
}
