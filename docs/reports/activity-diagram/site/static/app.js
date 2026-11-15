"use strict";

const MIN_SCALE = 0.1;
const MAX_SCALE = 6;
const FLOW_CELL = /^m_((?:WF|SF)\d\d)(?:_id|_name)?$/;

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/* Navigation bar: the menu button on small screens, one dropdown open at a time, Escape and outside clicks close it. */
function setupNavbar() {
    const toggle = document.querySelector(".menu-toggle");
    const menu = document.getElementById("menu");
    const dropdowns = [...document.querySelectorAll(".dropdown")];
    toggle.addEventListener("click", () => {
        const open = menu.classList.toggle("open");
        toggle.setAttribute("aria-expanded", String(open));
    });
    for (const dropdown of dropdowns) {
        dropdown.addEventListener("toggle", () => {
            if (dropdown.open) {
                dropdowns.filter((other) => other !== dropdown).forEach((other) => (other.open = false));
            }
        });
    }
    document.addEventListener("click", (event) => {
        dropdowns.filter((d) => d.open && !d.contains(event.target)).forEach((d) => (d.open = false));
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }
        const open = dropdowns.find((d) => d.open);
        if (open) {
            open.open = false;
            open.querySelector("summary").focus();
        }
    });
}

/* A diagram that can be moved by dragging and zoomed with the buttons, Ctrl + scroll, pinch or the keyboard. */
class Viewer {
    constructor(root) {
        this.root = root;
        this.canvas = root.querySelector(".canvas");
        this.stage = root.querySelector(".stage");
        this.level = root.querySelector(".zoom-level");
        this.openLink = root.querySelector(".open");
        this.flows = root.dataset.map ? JSON.parse(root.dataset.map) : null;
        this.scale = 1;
        this.x = 0;
        this.y = 0;
        this.width = 0;
        this.height = 0;
        this.fitted = true;
        this.pointers = new Map();
        root.querySelectorAll("[data-zoom]").forEach((button) =>
            button.addEventListener("click", () => this.command(button.dataset.zoom)));
        this.bindPointer();
        this.bindKeys();
        new ResizeObserver(() => this.fitted && this.fit()).observe(this.canvas);
    }

    async load(src) {
        this.openLink.href = src;
        this.root.classList.remove("failed");
        this.root.classList.add("loading");
        this.stage.replaceChildren();
        try {
            const response = await fetch(src);
            if (!response.ok) {
                throw new Error(response.statusText);
            }
            const parsed = new DOMParser().parseFromString(await response.text(), "image/svg+xml").documentElement;
            const box = (parsed.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
            this.width = box[2] || parseFloat(parsed.getAttribute("width"));
            this.height = box[3] || parseFloat(parsed.getAttribute("height"));
            parsed.setAttribute("width", this.width);
            parsed.setAttribute("height", this.height);
            const svg = document.importNode(parsed, true);
            svg.style.colorScheme = "light";
            this.stage.replaceChildren(svg);
            if (this.flows) {
                this.linkFlows(svg);
            }
            this.fit();
        } catch (error) {
            this.root.classList.add("failed");
            console.error(`Cannot load ${src}`, error);
        } finally {
            this.root.classList.remove("loading");
        }
    }

    apply() {
        this.stage.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.scale})`;
        this.level.textContent = `${Math.round(this.scale * 100)}%`;
    }

    /* Fit the diagram in the canvas; a diagram that fills the width first, as on a phone, gets a canvas as high as it. */
    fit() {
        this.canvas.style.height = "";
        const rect = this.canvas.getBoundingClientRect();
        if (!this.width || !rect.width) {
            return;
        }
        const pad = 24;
        const byWidth = (rect.width - 2 * pad) / this.width;
        const byHeight = (rect.height - 2 * pad) / this.height;
        this.scale = clamp(Math.min(byWidth, byHeight), MIN_SCALE, 1.5);
        this.x = (rect.width - this.width * this.scale) / 2;
        if (byWidth < byHeight) {
            this.canvas.style.height = `${Math.max(240, Math.ceil(this.height * this.scale + 2 * pad))}px`;
            this.y = pad;
        } else {
            this.y = (rect.height - this.height * this.scale) / 2;
        }
        this.fitted = true;
        this.apply();
    }

    zoomAt(factor, cx, cy) {
        const scale = clamp(this.scale * factor, MIN_SCALE, MAX_SCALE);
        const ratio = scale / this.scale;
        this.x = cx - (cx - this.x) * ratio;
        this.y = cy - (cy - this.y) * ratio;
        this.scale = scale;
        this.fitted = false;
        this.apply();
    }

    panBy(dx, dy) {
        this.x += dx;
        this.y += dy;
        this.fitted = false;
        this.apply();
    }

    command(name) {
        const rect = this.canvas.getBoundingClientRect();
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        if (name === "in") {
            this.zoomAt(1.25, cx, cy);
        } else if (name === "out") {
            this.zoomAt(0.8, cx, cy);
        } else if (name === "actual") {
            this.zoomAt(1 / this.scale, cx, cy);
        } else {
            this.fit();
        }
    }

    bindPointer() {
        const canvas = this.canvas;
        canvas.addEventListener("pointerdown", (event) => {
            if (event.pointerType === "mouse" && event.button !== 0) {
                return;
            }
            this.suppressClick = false;
            this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
            if (this.pointers.size === 1) {
                this.dragging = false;
                this.start = { x: event.clientX, y: event.clientY, left: this.x, top: this.y };
            } else if (this.pointers.size === 2) {
                const [a, b] = this.pointers.values();
                this.pinch = { distance: distance(a, b), scale: this.scale };
                this.dragging = true;
            }
        });
        canvas.addEventListener("pointermove", (event) => {
            if (!this.pointers.has(event.pointerId)) {
                return;
            }
            this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
            if (this.pinch && this.pointers.size === 2) {
                const [a, b] = this.pointers.values();
                const rect = canvas.getBoundingClientRect();
                const target = this.pinch.scale * distance(a, b) / this.pinch.distance;
                this.zoomAt(target / this.scale, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
                return;
            }
            const dx = event.clientX - this.start.x;
            const dy = event.clientY - this.start.y;
            if (!this.dragging && Math.hypot(dx, dy) > 4) {
                this.dragging = true;
                canvas.setPointerCapture(event.pointerId);
                canvas.classList.add("dragging");
            }
            if (this.dragging) {
                this.x = this.start.left + dx;
                this.y = this.start.top + dy;
                this.fitted = false;
                this.apply();
            }
        });
        const end = (event) => {
            this.pointers.delete(event.pointerId);
            if (this.pointers.size < 2) {
                this.pinch = null;
            }
            if (this.pointers.size === 1) {
                const [rest] = this.pointers.values();
                this.start = { x: rest.x, y: rest.y, left: this.x, top: this.y };
            } else if (this.pointers.size === 0) {
                canvas.classList.remove("dragging");
                this.suppressClick = this.dragging;
            }
        };
        canvas.addEventListener("pointerup", end);
        canvas.addEventListener("pointercancel", end);
        canvas.addEventListener("click", (event) => {
            if (this.suppressClick) {
                event.stopPropagation();
                event.preventDefault();
                this.suppressClick = false;
            }
        }, true);
        canvas.addEventListener("wheel", (event) => {
            if (!event.ctrlKey && !event.metaKey) {
                return;
            }
            event.preventDefault();
            const rect = canvas.getBoundingClientRect();
            this.zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX - rect.left, event.clientY - rect.top);
        }, { passive: false });
    }

    bindKeys() {
        this.canvas.addEventListener("keydown", (event) => {
            const moves = { ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60] };
            if (event.target !== this.canvas) {
                return;
            }
            if (event.key === "+" || event.key === "=") {
                this.command("in");
            } else if (event.key === "-") {
                this.command("out");
            } else if (event.key === "0") {
                this.command("fit");
            } else if (moves[event.key]) {
                this.panBy(...moves[event.key]);
            } else {
                return;
            }
            event.preventDefault();
        });
    }

    /* Each flow of the map opens its page; its box and its text light up together. */
    linkFlows(svg) {
        const groups = {};
        for (const cell of svg.querySelectorAll("g[data-cell-id]")) {
            const match = FLOW_CELL.exec(cell.getAttribute("data-cell-id"));
            if (match && this.flows[match[1]]) {
                cell.dataset.flow = match[1];
                (groups[match[1]] ||= []).push(cell);
            }
        }
        let current = null;
        const highlight = (key) => {
            if (key === current) {
                return;
            }
            groups[current]?.forEach((cell) => cell.classList.remove("is-hover"));
            current = key;
            groups[current]?.forEach((cell) => cell.classList.add("is-hover"));
        };
        const open = (key) => {
            window.location.href = this.flows[key].href;
        };
        for (const [key, cells] of Object.entries(groups)) {
            const main = cells.find((cell) => cell.getAttribute("data-cell-id") === `m_${key}`) || cells[0];
            const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
            title.textContent = this.flows[key].title;
            main.prepend(title);
            main.setAttribute("tabindex", "0");
            main.setAttribute("role", "link");
            main.setAttribute("aria-label", this.flows[key].title);
            main.addEventListener("focus", () => highlight(key));
            main.addEventListener("blur", () => highlight(null));
            main.addEventListener("keydown", (event) => {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    open(key);
                }
            });
        }
        svg.addEventListener("pointerover", (event) => highlight(event.target.closest("[data-flow]")?.dataset.flow ?? null));
        svg.addEventListener("pointerleave", () => highlight(null));
        svg.addEventListener("click", (event) => {
            const key = event.target.closest("[data-flow]")?.dataset.flow;
            if (key) {
                open(key);
            }
        });
    }
}

/* The Workflow and Demo scenarios tabs of a core flow; the address keeps the open tab. */
function setupTabs(viewer) {
    const tabs = [...document.querySelectorAll('.tabs [role="tab"]')];
    if (!tabs.length) {
        return false;
    }
    const select = (tab, remember) => {
        tabs.forEach((other) => {
            other.setAttribute("aria-selected", String(other === tab));
            other.tabIndex = other === tab ? 0 : -1;
        });
        viewer.canvas.setAttribute("aria-label", `${document.querySelector('.breadcrumb [aria-current="page"]').textContent}, ${tab.textContent}`);
        viewer.load(tab.dataset.src);
        if (remember) {
            history.replaceState(null, "", `#${tab.dataset.hash}`);
        }
    };
    tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => select(tab, true));
        tab.addEventListener("keydown", (event) => {
            const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
            if (step) {
                const next = tabs[(index + step + tabs.length) % tabs.length];
                next.focus();
                select(next, true);
            }
        });
    });
    select(tabs.find((tab) => `#${tab.dataset.hash}` === window.location.hash) || tabs[0], false);
    return true;
}

document.addEventListener("DOMContentLoaded", () => {
    setupNavbar();
    const root = document.querySelector(".viewer");
    if (root) {
        const viewer = new Viewer(root);
        if (!setupTabs(viewer)) {
            viewer.load(root.dataset.src);
        }
    }
});
