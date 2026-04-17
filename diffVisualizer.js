/**
 * Diff Visualizer - Interactive overlay for navigating document changes
 * Provides controls for:
 * - Navigate between changes (previous/next)
 * - Toggle between changes, original, and simple views
 */

class DiffVisualizer {
  static ViewMode = {
    ALL: "all",
    ORIGINAL: "original",
    SIMPLE: "simple",
  };
  static ClassesMode = {
    ALL: "diff-view-all",
    ORIGINAL: "diff-view-original",
    SIMPLE: "diff-view-simple",
    BASE: "diff-view-",
  }
  constructor() {
    this.currentChangeIndex = 0;
    this.changes = [];
    this.viewMode = DiffVisualizer.ViewMode.ALL;
    this._removedCssRules = [];
    this.init();
  }

  init() {
    this.createOverlayButton();
    this.createOverlay();
    this.findChanges();
    this.storeOriginalContent();
    this.attachEventListeners();
    this.applyViewMode();
    this.updateDiffChangesState();
    // Highlight the first change on load
    if (this.changes.length > 0) {
      this.highlightChange(this.changes[0]);
    }
  }

  /**
   * Stores the original HTML content of changed elements for Original view
   */
  storeOriginalContent() {
    document.querySelectorAll("del").forEach((el) => {
      const parent = el.parentElement;
      if (!parent) return;

      // Store original content (text from del element)
      if (!parent.dataset.originalContent) {
        parent.dataset.originalContent = el.textContent;
      }
    });
  }

  /**
   * Creates the button in the top right corner
   */
  createOverlayButton() {
    const button = document.createElement("button");
    button.id = "diff-visualizer-btn";
    button.className = "diff-visualizer-btn";
    button.innerHTML = "⚙️ Diff Controls";
    button.setAttribute("aria-label", "Open diff visualizer controls");

    document.body.appendChild(button);

    button.addEventListener("click", () => {
      const overlay = document.getElementById("diff-visualizer-overlay");
      const isVisible = overlay.classList.contains("visible");
      if (isVisible) {
        overlay.classList.remove("visible");
      } else {
        overlay.classList.add("visible");
      }
    });
  }

  /**
   * Creates the overlay with control buttons
   */
  createOverlay() {
    const overlay = document.createElement("div");
    overlay.id = "diff-visualizer-overlay";
    overlay.className = "diff-visualizer-overlay";

    overlay.innerHTML = `
      <div class="diff-visualizer-panel">
      <div class="diff-visualizer-header">
        <h2>Diff Controls</h2>
        <button class="diff-close-btn" aria-label="Close overlay">&times;</button>
      </div>
      
      <div class="diff-visualizer-section" id="diff-navigation-section">
        <h3>Navigate Changes</h3>
        <div class="diff-visualizer-nav">
        <button id="diff-prev-btn" class="diff-nav-btn" title="Go to previous change">
          ← Previous
        </button>
        <div class="diff-change-counter">
          <span id="diff-change-current">0</span> / <span id="diff-change-total">0</span>
        </div>
        <button id="diff-next-btn" class="diff-nav-btn" title="Go to next change">
          Next →
        </button>
        <div class="diff-highlight-toggle">
          <input type="checkbox" id="diff-highlight-toggle" checked/>
          <label for="diff-highlight-toggle" title="Toggle highlight on current change">Highlight</label>
        </div>
        </div>
      </div>
      
      <div class="diff-visualizer-section">
        <h3>View Mode</h3>
        <div class="diff-visualizer-modes">
        <button class="diff-mode-btn active" data-mode="${DiffVisualizer.ViewMode.ALL}" title="Show all changes (new and original)">
          All
        </button>
        <button class="diff-mode-btn" data-mode="${DiffVisualizer.ViewMode.SIMPLE}" title="Show only updated values">
          Simple
        </button>
        <button class="diff-mode-btn" data-mode="${DiffVisualizer.ViewMode.ORIGINAL}" title="Show original document only">
          Original
        </button>
        </div>
      </div>
      
      <div class="diff-visualizer-section">
        <div class="diff-visualizer-stats">
        <p>Total Changes: <strong id="diff-total-count">0</strong></p>
        </div>
      </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Close button handler
    overlay.querySelector(".diff-close-btn").addEventListener("click", () => {
      overlay.classList.remove("visible");
    });
  }

  /**
   * Finds all changed elements in the document
   */
  findChanges() {
    // Look for ins (additions) and del (deletions) tags
    const insertions = document.querySelectorAll("ins");
    const deletions = document.querySelectorAll("del");
    const rowAdditions = document.querySelectorAll("tr.row-added");
    const rowDeletions = document.querySelectorAll("tr.row-removed");

    // Create a Set to avoid duplicates
    const insertionsSet = new Set(insertions);
    rowAdditions.forEach((el) => insertionsSet.add(el));

    const deletionsSet = new Set(deletions);
    rowDeletions.forEach((el) => deletionsSet.add(el));

    // Use Sets to avoid duplicates
    const insertionsFinal = insertionsSet;
    const deletionsFinal = deletionsSet;

    // Combine and sort by document order
    const allChanges = Array.from(insertionsFinal).concat(
      Array.from(deletionsFinal)
    );

    // Sort by position in document
    this.changes = allChanges.sort((a, b) => {
      return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING
        ? -1
        : 1;
    });
    const diffBtn = document.getElementById("diff-visualizer-btn");
    if (this.changes.length > 0) {
      diffBtn.style.display = "block";
    } else {
      diffBtn.style.display = "none";
    }
    this.updateChangeCounter();
  }

  /**
   * Updates the change counter display
   */
  updateChangeCounter() {
    const totalCount = document.getElementById("diff-total-count");
    const currentCount = document.getElementById("diff-change-current");
    const totalDisplay = document.getElementById("diff-change-total");

    if (totalCount) totalCount.textContent = this.changes.length;
    if (totalDisplay) totalDisplay.textContent = this.changes.length;
    if (currentCount)
      currentCount.textContent =
        this.changes.length > 0 ? this.currentChangeIndex + 1 : 0;
  }

  /**
   * Scrolls to the current change element
   */
  scrollToChange() {
    if (this.changes.length === 0) return;

    const element = this.changes[this.currentChangeIndex];
    element.scrollIntoView({ behavior: "smooth", block: "center" });

    // Highlight the current change temporarily
    this.highlightChange(element);
    this.updateChangeCounter();
  }

  /**
   * Highlights a changed element
   */
  highlightChange(element) {
    // Remove previous highlight
    document
      .querySelectorAll(".diff-current-highlight-selected")
      .forEach((el) => {
        el.classList.remove("diff-current-highlight-selected");
        this.removeHighlightElement(el);
      });

    // Add highlight to current element
    element.classList.add("diff-current-highlight-selected");
    if (document.getElementById("diff-highlight-toggle").checked)
      this.highlightElement(element);
  }

  /**
   * Navigate to next change
   */
  nextChange() {
    if (this.changes.length === 0) return;
    if (this.viewMode === DiffVisualizer.ViewMode.SIMPLE) {
      let nextIndex = (this.currentChangeIndex + 1) % this.changes.length;
      // Skip deletions
      while (
        this.changes[nextIndex].tagName.toLowerCase() === "del" ||
        this.changes[nextIndex].closest("tr.row-removed")
      ) {
        nextIndex = (nextIndex + 1) % this.changes.length;
        if (nextIndex === this.currentChangeIndex) break; // Avoid infinite loop
      }
      this.currentChangeIndex = nextIndex;
    }
    if (this.viewMode === DiffVisualizer.ViewMode.ALL) {
      this.currentChangeIndex =
        (this.currentChangeIndex + 1) % this.changes.length;
    }
    this.scrollToChange();
  }

  /**
   * Navigate to previous change
   */
  prevChange() {
    if (this.changes.length === 0) return;
    if (this.viewMode === DiffVisualizer.ViewMode.SIMPLE) {
      let prevIndex =
        (this.currentChangeIndex - 1 + this.changes.length) %
        this.changes.length;
      // Skip deletions
      while (
        this.changes[prevIndex].tagName.toLowerCase() === "del" ||
        this.changes[prevIndex].closest("tr.row-removed")
      ) {
        prevIndex = (prevIndex - 1 + this.changes.length) % this.changes.length;
        if (prevIndex === this.currentChangeIndex) break; // Avoid infinite loop
      }
      this.currentChangeIndex = prevIndex;
    }
    if (this.viewMode === "all") {
      this.currentChangeIndex =
        (this.currentChangeIndex - 1 + this.changes.length) %
        this.changes.length;
    }
    this.scrollToChange();
  }

  /**
   * Changes the view mode
   */
  setViewMode(mode) {
    const prev_mode = this.viewMode;
    this.viewMode = mode;

    // Update button states
    document.querySelectorAll(".diff-mode-btn").forEach((btn) => {
      btn.classList.remove("active");
      if (btn.getAttribute("data-mode") === mode) {
        btn.classList.add("active");
      }
    });
    if (mode === DiffVisualizer.ViewMode.ORIGINAL) {
      document.getElementById("diff-navigation-section").style.display = "none";
      if (document.getElementById("diff-highlight-toggle").checked)
        this.removeHighlightFromAny();
    } else {
      document.getElementById("diff-navigation-section").style.display =
        "block";
      if (document.getElementById("diff-highlight-toggle").checked)
        this.highlightSelected();
    }
    this.updateChangeCounter();
    this.applyViewMode(prev_mode);
    this.updateDiffChangesState();
  }

  updateDiffChangesState() {
    const enable = this.viewMode !== DiffVisualizer.ViewMode.ORIGINAL;
    document
      .querySelectorAll(".diff-changes-enable, .diff-changes-disable")
      .forEach((el) => {
        if (enable) {
          el.classList.add("diff-changes-enable");
          el.classList.remove("diff-changes-disable");
        } else {
          el.classList.add("diff-changes-disable");
          el.classList.remove("diff-changes-enable");
        }
      });
  }

  /**
   * Applies the current view mode
   */
  applyViewMode(prev_mode) {
    const body = document.body;

    body.classList.remove(
      DiffVisualizer.ClassesMode.ALL,
      DiffVisualizer.ClassesMode.ORIGINAL,
      DiffVisualizer.ClassesMode.SIMPLE
    );
    body.classList.add(`${DiffVisualizer.ClassesMode.BASE}${this.viewMode}`);

    if (!prev_mode) prev_mode = DiffVisualizer.ViewMode.ALL;
    if (prev_mode === this.viewMode) return;
    this.changes.forEach((el) => {
      el.classList.remove(`${DiffVisualizer.ClassesMode.BASE}${prev_mode}`);
      el.classList.add(`${DiffVisualizer.ClassesMode.BASE}${this.viewMode}`);
    });
    // Update table rows with row-added and row-removed
    document.querySelectorAll("tr.row-added, tr.row-removed").forEach((el) => {
      el.classList.remove(`${DiffVisualizer.ClassesMode.BASE}${prev_mode}`);
      el.classList.add(`${DiffVisualizer.ClassesMode.BASE}${this.viewMode}`);
    });
  }

  /**
   * Attaches event listeners to all control buttons
   */
  attachEventListeners() {
    // Navigation buttons
    const prevBtn = document.getElementById("diff-prev-btn");
    const nextBtn = document.getElementById("diff-next-btn");
    const highlightToggle = document.getElementById("diff-highlight-toggle");

    // Highlight toggle
    if (highlightToggle) {
      highlightToggle.addEventListener("change", (e) => {
        document
          .querySelectorAll(".diff-current-highlight-selected")
          .forEach((el) => {
            if (e.target.checked) {
              this.highlightElement(el);
            } else {
              this.removeHighlightElement(el);
            }
          });
      });
    }

    // Previous/Next buttons

    if (prevBtn) prevBtn.addEventListener("click", () => this.prevChange());
    if (nextBtn) nextBtn.addEventListener("click", () => this.nextChange());

    // Mode buttons
    document.querySelectorAll(".diff-mode-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        this.setViewMode(e.target.getAttribute("data-mode"));
      });
    });

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      // Ctrl + right arrow = next change
      if (e.ctrlKey && e.key === "ArrowRight") {
        e.preventDefault();
        if (this.viewMode === DiffVisualizer.ViewMode.ORIGINAL) return;
        this.nextChange();
      }
      // Ctrl + left arrow = previous change
      if (e.ctrlKey && e.key === "ArrowLeft") {
        e.preventDefault();
        if (this.viewMode === DiffVisualizer.ViewMode.ORIGINAL) return;
        this.prevChange();
      }
      // Ctrl + Q = toggle overlay
      if (e.ctrlKey && e.key === "q") {
        e.preventDefault();
        const overlay = document.getElementById("diff-visualizer-overlay");
        overlay.classList.toggle("visible");
      }
    });
  }

  highlightElement(element) {
    element.classList.add("diff-current-highlight");
  }

  removeHighlightElement(element) {
    element.classList.remove("diff-current-highlight");
  }

  removeHighlightFromAny() {
    document
      .querySelectorAll(".diff-current-highlight")
      .forEach((el) => el.classList.remove("diff-current-highlight"));
  }

  highlightSelected() {
    document
      .querySelectorAll(".diff-current-highlight-selected")
      .forEach((el) => this.highlightElement(el));
  }
}

// Initialize when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    new DiffVisualizer();
  });
} else {
  new DiffVisualizer();
}
