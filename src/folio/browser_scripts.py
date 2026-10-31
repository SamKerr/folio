"""JavaScript snippets executed in the browser via Playwright.

Each script must be a valid arrow-function expression. Syntax is validated in
tests/test_browser_scripts.py using Node.js.
"""

EXTRACT_ASSET_URLS = """
() => {
    const urls = new Set();
    const add = (value, base) => {
        if (!value || value.startsWith("data:") || value.startsWith("blob:")) {
            return;
        }
        try {
            urls.add(new URL(value, base).href);
        } catch (error) {
            return;
        }
    };

    const urlPattern = /url\\(\\s*['"]?([^'")]+?)['"]?\\s*\\)/gi;
    const attrNames = [
        "href", "poster", "data-src", "data-lazy-src",
        "data-srcset", "data-background", "data-bg", "content",
    ];

    for (const element of document.querySelectorAll("*")) {
        if (element.tagName === "VIDEO" || element.tagName === "AUDIO") {
            continue;
        }
        if (element.tagName === "SOURCE") {
            const parent = element.parentElement;
            if (parent && (parent.tagName === "VIDEO" || parent.tagName === "AUDIO")) {
                continue;
            }
        }
        for (const name of attrNames) {
            if (name === "href" && element.tagName === "A") {
                continue;
            }
            add(element.getAttribute(name), document.baseURI);
        }
        if (element.tagName !== "SOURCE") {
            add(element.getAttribute("src"), document.baseURI);
        }
        if (element.tagName === "OBJECT") {
            add(element.getAttribute("data"), document.baseURI);
        }
        const srcset = element.getAttribute("srcset");
        if (srcset) {
            for (const item of srcset.split(",")) {
                const url = item.trim().split(/\\s+/)[0];
                add(url, document.baseURI);
            }
        }
        const style = element.getAttribute("style");
        if (style) {
            for (const match of style.matchAll(urlPattern)) {
                add(match[1], document.baseURI);
            }
        }
    }

    for (const use of document.querySelectorAll("use, image")) {
        add(use.getAttribute("href"), document.baseURI);
        add(use.getAttribute("xlink:href"), document.baseURI);
    }

    for (const sheet of document.styleSheets) {
        try {
            for (const rule of sheet.cssRules || []) {
                if (!rule.style) {
                    continue;
                }
                const bg = rule.style.backgroundImage || rule.style.content;
                const mask = rule.style.maskImage || rule.style.webkitMaskImage;
                for (const value of [bg, mask]) {
                    if (!value) {
                        continue;
                    }
                    for (const match of value.matchAll(urlPattern)) {
                        add(match[1], document.baseURI);
                    }
                }
            }
        } catch (error) {
            continue;
        }
    }

    return [...urls];
}
"""

SCROLL_PAGE = """
async () => {
    await new Promise((resolve) => {
        const maxScroll = Math.max(
            document.body?.scrollHeight ?? 0,
            document.documentElement?.scrollHeight ?? 0,
        );
        let y = 0;
        const step = () => {
            y += window.innerHeight;
            window.scrollTo(0, y);
            if (y < maxScroll) {
                requestAnimationFrame(step);
            } else {
                window.scrollTo(0, 0);
                resolve(null);
            }
        };
        step();
    });
}
"""

WAIT_FOR_IMAGES = """
async (timeoutMs) => {
    const lazySrcAttrs = [
        "data-src", "data-lazy-src", "data-original", "data-url", "data-image",
    ];
    const lazySrcsetAttrs = ["data-srcset", "data-lazy-srcset"];

    const promoteLazyImages = () => {
        for (const img of document.querySelectorAll("img")) {
            for (const attr of lazySrcAttrs) {
                const lazy = img.getAttribute(attr);
                const src = img.getAttribute("src") || "";
                if (lazy && (!src || src.startsWith("data:"))) {
                    img.setAttribute("src", lazy);
                }
            }
            if (img.loading === "lazy") {
                img.loading = "eager";
            }
        }
        for (const source of document.querySelectorAll("source")) {
            for (const attr of lazySrcsetAttrs) {
                const lazy = source.getAttribute(attr);
                if (lazy && !source.getAttribute("srcset")) {
                    source.setAttribute("srcset", lazy);
                }
            }
        }
    };

    const isImageSettled = (img) => {
        if (!img.getAttribute("src") && !img.currentSrc) {
            return true;
        }
        if (img.complete) {
            return img.naturalWidth > 0 || img.naturalHeight === 0;
        }
        return false;
    };

    const waitForImage = (img) => new Promise((resolve) => {
        if (isImageSettled(img)) {
            resolve(null);
            return;
        }
        const done = () => resolve(null);
        img.addEventListener("load", done, { once: true });
        img.addEventListener("error", done, { once: true });
        setTimeout(done, timeoutMs);
    });

    for (let round = 0; round < 3; round += 1) {
        promoteLazyImages();
        await Promise.all([...document.images].map(waitForImage));
        const pending = [...document.images].filter((img) => !isImageSettled(img));
        if (pending.length === 0) {
            break;
        }
    }
}
"""

WAIT_FOR_DIAGRAMS = """
async (timeoutMs) => {
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const hasDiagramContent = (el) => {
        if (el.querySelector("svg metadata, svg path, svg text, img[src]")) {
            return true;
        }
        const svg = el.querySelector("svg[viewBox], svg[viewbox]");
        return Boolean(svg && svg.querySelector("path, text, rect, circle, line"));
    };

    const isDiagramPlaceholder = (el) => {
        if (!el.matches('[role="img"]')) {
            return false;
        }
        if (hasDiagramContent(el)) {
            return false;
        }
        if (
            el.classList.contains("animate-pulse")
            || el.classList.contains("bg-action-hover")
        ) {
            return true;
        }
        const style = el.getAttribute("style") || "";
        return style.includes("aspect-ratio");
    };

    const pendingDiagrams = () => {
        return [...document.querySelectorAll('[role="img"]')]
            .filter(isDiagramPlaceholder);
    };

    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        const pending = pendingDiagrams();
        if (pending.length === 0) {
            return;
        }
        for (const el of pending) {
            el.scrollIntoView({ block: "center", inline: "nearest" });
        }
        await delay(200);
    }
}
"""

_CHEVRON_LOGIC = """
    const CHEVRON_NAME_PATTERN = /chevron|caret-down|caret-up|caret-right|caret-left|caret/i;
    const CHEVRON_CHAR_PATTERN = /^[\\s\\u203A\\u2039\\u25BE\\u25B8\\u25BC\\u25B2\\u25BA\\u25C4\\u2304\\u2303▼▾▸◂▶◀▲▼›‹»«↓↑→←]+$/;

    const chevronHint = (element) => [
        element.getAttribute("class") || "",
        element.getAttribute("id") || "",
        element.getAttribute("data-icon") || "",
        element.getAttribute("data-lucide") || "",
        element.getAttribute("aria-label") || "",
        element.parentElement?.getAttribute("class") || "",
    ].join(" ");

    const isChevronSvg = (element) => {
        if (element.tagName !== "svg") {
            return false;
        }
        return CHEVRON_NAME_PATTERN.test(chevronHint(element));
    };

    const isChevronText = (element) => {
        if (element.children.length > 0) {
            return false;
        }
        const text = (element.textContent || "").trim();
        return text.length > 0 && text.length <= 2 && CHEVRON_CHAR_PATTERN.test(text);
    };

    const findChevrons = () => {
        const chevrons = [];
        for (const svg of document.querySelectorAll("svg")) {
            if (isChevronSvg(svg)) {
                chevrons.push(svg);
            }
        }
        for (const element of document.querySelectorAll("span, i, em, small")) {
            if (isChevronText(element)) {
                chevrons.push(element);
            }
        }
        return chevrons;
    };

    const isChevronExpanded = (chevron) => {
        const control = chevron.closest("[aria-expanded], [data-state], details");
        if (control?.getAttribute("aria-expanded") === "true") {
            return true;
        }
        if (control?.getAttribute("data-state") === "open") {
            return true;
        }
        if (control?.tagName === "DETAILS" && control.open) {
            return true;
        }
        if (chevron.tagName === "svg") {
            return [...chevron.classList].some(
                (className) => className.startsWith("rotate-") && className !== "rotate-0",
            );
        }
        return false;
    };

    const shouldSkipChevron = (chevron) => {
        if (isChevronExpanded(chevron)) {
            return true;
        }
        return Boolean(chevron.closest("a[href]"));
    };
"""

INTERACT_WITH_PAGE = (
    """
async (delayMs) => {
"""
    + _CHEVRON_LOGIC
    + """
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const clicked = new WeakSet();

    const safeClick = async (element) => {
        if (clicked.has(element)) {
            return;
        }
        clicked.add(element);
        try {
            element.scrollIntoView({ block: "center", inline: "nearest" });
            element.click();
            await delay(delayMs);
        } catch (error) {
            return;
        }
    };

    const expandCollapsedChevrons = async () => {
        let expandedAny = false;
        for (const chevron of findChevrons()) {
            if (shouldSkipChevron(chevron)) {
                continue;
            }
            await safeClick(chevron);
            expandedAny = true;
        }
        return expandedAny;
    };

    for (let pass = 0; pass < 5; pass += 1) {
        const expandedAny = await expandCollapsedChevrons();
        if (!expandedAny) {
            break;
        }
    }
}
"""
)

DISCOVER_LINKS_WITH_INTERACTION = (
    """
async (delayMs) => {
"""
    + _CHEVRON_LOGIC
    + """
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const links = new Set();
    const clicked = new WeakSet();

    const addLinks = () => {
        for (const anchor of document.querySelectorAll("a[href]")) {
            const href = anchor.href;
            if (href && !href.startsWith("javascript:")) {
                links.add(href);
            }
        }
        // Pagination that is not an anchor: <link rel="next|prev" href=...>.
        for (const link of document.querySelectorAll(
            'link[rel~="next"][href], link[rel~="prev"][href]'
        )) {
            if (link.href) {
                links.add(link.href);
            }
        }
    };

    const safeClick = async (element) => {
        if (clicked.has(element)) {
            return;
        }
        clicked.add(element);
        try {
            element.scrollIntoView({ block: "center", inline: "nearest" });
            element.click();
            await delay(delayMs);
            addLinks();
        } catch (error) {
            return;
        }
    };

    const expandCollapsedChevrons = async () => {
        let expandedAny = false;
        for (const chevron of findChevrons()) {
            if (shouldSkipChevron(chevron)) {
                continue;
            }
            await safeClick(chevron);
            expandedAny = true;
        }
        return expandedAny;
    };

    addLinks();

    for (let pass = 0; pass < 5; pass += 1) {
        const expandedAny = await expandCollapsedChevrons();
        if (!expandedAny) {
            break;
        }
    }

    addLinks();
    return [...links];
}
"""
)

BROWSER_SCRIPTS = {
    "extract_asset_urls": EXTRACT_ASSET_URLS,
    "scroll_page": SCROLL_PAGE,
    "wait_for_images": WAIT_FOR_IMAGES,
    "wait_for_diagrams": WAIT_FOR_DIAGRAMS,
    "interact_with_page": INTERACT_WITH_PAGE,
    "discover_links_with_interaction": DISCOVER_LINKS_WITH_INTERACTION,
}
