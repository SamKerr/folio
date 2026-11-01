// Folio web UI — Vue 3, no build step. Talks to folio.webui.server.
import {
  createApp,
  reactive,
  computed,
  ref,
  watch,
  nextTick,
  onMounted,
  onBeforeUnmount,
} from "vue";

const TOKEN = window.FOLIO_TOKEN;
const STORAGE_KEY = "folio.form.v1";
const LOG_LIMIT = 2000;
const ACTIVE_STATES = new Set(["running", "waiting_login", "stopping"]);
const PRESET_NAMES = ["Fast", "Balanced", "Thorough"];
const TIMING_FIELDS = [
  { key: "image_wait_ms", label: "Image wait", unit: "ms" },
  { key: "asset_quiet_ms", label: "Asset quiet", unit: "ms" },
  { key: "page_asset_timeout_ms", label: "Page asset cap", unit: "ms" },
  { key: "settle_ms", label: "Settle", unit: "ms" },
  { key: "timeout_secs", label: "Page timeout", unit: "s" },
];

// -- API ---------------------------------------------------------------------

async function api(path, body) {
  const init = { headers: { "X-Folio-Token": TOKEN } };
  if (body !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  let data = {};
  try {
    data = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.status = res.status;
    err.field = data.field;
    throw err;
  }
  return data;
}

// -- Store -------------------------------------------------------------------

const store = reactive({
  config: null,
  view: "crawl",
  showForm: true,
  session: { state: "idle", progress: {} },
  log: [],
  sites: [],
  libraryDir: "",
  libraryLoading: false,
  toasts: [],
  form: {
    url: "",
    output_dir: "",
    preset: "Balanced",
    concurrency: 20,
    asset_concurrency: 12,
    max_pages: "",
    force: false,
    exclude_patterns: "",
    image_wait_ms: 5000,
    asset_quiet_ms: 750,
    page_asset_timeout_ms: 60000,
    settle_ms: 1000,
    timeout_secs: 60,
  },
});

let toastId = 0;
function toast(message, kind = "info") {
  const id = ++toastId;
  store.toasts.push({ id, message, kind });
  setTimeout(() => {
    store.toasts = store.toasts.filter((t) => t.id !== id);
  }, 4500);
}

function loadSavedForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && typeof saved === "object") Object.assign(store.form, saved);
  } catch {
    /* storage unavailable */
  }
}

function saveForm() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store.form));
  } catch {
    /* storage unavailable */
  }
}

async function refreshLibrary() {
  store.libraryLoading = true;
  try {
    const q = encodeURIComponent(store.form.output_dir || "");
    const data = await api(`/api/library?output=${q}`);
    store.sites = data.sites;
    store.libraryDir = data.output_dir;
  } catch (err) {
    toast(err.message, "error");
  } finally {
    store.libraryLoading = false;
  }
}

async function openSite(host, outputDir) {
  try {
    await api("/api/library/open", {
      host,
      output_dir: outputDir || store.form.output_dir,
    });
  } catch (err) {
    toast(err.message, "error");
  }
}

function connectEvents() {
  const source = new EventSource(`/api/events?token=${encodeURIComponent(TOKEN)}`);
  source.onmessage = (msg) => {
    const event = JSON.parse(msg.data);
    if (event.type === "state") {
      const prev = store.session.state;
      store.session = event.session;
      if (prev !== event.session.state && event.session.state === "finished") {
        refreshLibrary();
      }
    } else if (event.type === "log") {
      store.log.push(event.line);
      if (store.log.length > LOG_LIMIT) store.log.splice(0, store.log.length - LOG_LIMIT);
      if (event.progress) store.session.progress = event.progress;
    }
  };
}

// -- Helpers -----------------------------------------------------------------

function hueFor(text) {
  let h = 0;
  for (const ch of text || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h % 360;
}

// Colours from the Folio icon: card violet, gold, burgundy robe, green hood.
const AVATAR_COLOURS = [
  ["#6a5ab0", "#3f3378"],
  ["#d6aa45", "#9a7322"],
  ["#9a3a30", "#5e1f19"],
  ["#5d7040", "#34431f"],
  ["#7a6ac0", "#4f4296"],
];

function avatarStyle(host) {
  const [a, b] = AVATAR_COLOURS[hueFor(host) % AVATAR_COLOURS.length];
  return { background: `linear-gradient(135deg, ${a}, ${b})` };
}

function avatarLetter(host) {
  const name = (host || "?").replace(/^www\./, "");
  return name.charAt(0);
}

function relativeTime(epochSecs) {
  const diff = Date.now() / 1000 - epochSecs;
  const steps = [
    [60, "second"],
    [3600, "minute", 60],
    [86400, "hour", 3600],
    [604800, "day", 86400],
    [2629800, "week", 604800],
    [31557600, "month", 2629800],
    [Infinity, "year", 31557600],
  ];
  const fmt = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (diff < 45) return "just now";
  for (const [limit, unit, div = 1] of steps) {
    if (diff < limit) return fmt.format(-Math.round(diff / div), unit);
  }
  return "";
}

function formatDuration(secs) {
  secs = Math.max(0, Math.floor(secs));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = String(secs % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

function shortPath(path) {
  if (!path) return "";
  return path.replace(/^\/Users\/[^/]+/, "~");
}

const STATE_LABELS = {
  idle: "Idle",
  running: "Crawling",
  waiting_login: "Waiting for login",
  stopping: "Stopping…",
  finished: "Finished",
  failed: "Failed",
  stopped: "Stopped",
};

// -- Icons (Lucide-style paths) ------------------------------------------------

const ICONS = {
  plus: "M12 5v14M5 12h14",
  library: "M4 4v16M9 4v16M14 4l5 16M4 20h16",
  globe:
    "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20ZM2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10Z",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  folder: "M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z",
  gauge: "M12 14l4-4M3.3 19a10 10 0 1 1 17.4 0",
  filter: "M3 5h18l-7 8v6l-4 2v-8L3 5Z",
  sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4",
  chevronDown: "m6 9 6 6 6-6",
  key: "M15.5 7.5 19 4M21 2l-2 2M2 18.5a3.5 3.5 0 1 0 7 0 3.5 3.5 0 0 0-7 0ZM8 16l7.5-7.5 3 3L21 9",
  stop: "M6 6h12v12H6z",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18M6 6l12 12",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6ZM14 2v6h6",
  skip: "M5 4l10 8-10 8V4ZM19 5v14",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20ZM12 6v6l4 2",
  search: "M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM21 21l-4.3-4.3",
  refresh: "M21 12a9 9 0 0 1-15 6.7L3 16M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M3 21v-5h5",
  external: "M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
  rotate: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5",
  terminal: "m4 17 6-6-6-6M12 19h8",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3Z",
};

const Icon = {
  props: { name: String },
  setup(props) {
    return { d: computed(() => ICONS[props.name] || "") };
  },
  template: `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="d"/></svg>`,
};

// -- Crawl form ----------------------------------------------------------------

const CrawlForm = {
  components: { Icon },
  setup() {
    const form = store.form;
    const errors = reactive({});
    const submitting = ref(false);
    const advancedOpen = ref(form.preset === "Custom");

    const presetDescription = computed(() => {
      if (form.preset === "Custom") return "Your own timings — see Advanced timings below.";
      return store.config?.preset_descriptions?.[form.preset] || "";
    });

    function choosePreset(name) {
      form.preset = name;
      if (name === "Custom") {
        advancedOpen.value = true;
        return;
      }
      Object.assign(form, store.config.presets[name]);
    }

    function onTimingInput() {
      if (form.preset !== "Custom") form.preset = "Custom";
    }

    async function browse() {
      try {
        const { path } = await api("/api/pick-folder", {});
        if (path) {
          form.output_dir = path;
          refreshLibrary();
        }
      } catch (err) {
        toast(err.message, "error");
      }
    }

    async function start() {
      for (const key of Object.keys(errors)) delete errors[key];
      submitting.value = true;
      try {
        const session = await api("/api/crawl", { ...form });
        store.session = session;
        store.log = [];
        store.showForm = false;
        saveForm();
      } catch (err) {
        if (err.field) {
          errors[err.field] = err.message;
          if (TIMING_FIELDS.some((f) => f.key === err.field)) advancedOpen.value = true;
        } else {
          toast(err.message, "error");
        }
      } finally {
        submitting.value = false;
      }
    }

    return {
      store,
      form,
      errors,
      submitting,
      advancedOpen,
      presetDescription,
      choosePreset,
      onTimingInput,
      browse,
      start,
      PRESET_NAMES,
      TIMING_FIELDS,
    };
  },
  template: `
  <div class="page">
    <header class="page-header">
      <div>
        <h1>New crawl</h1>
        <p>Log in once, save the content, browse it offline.</p>
      </div>
    </header>

    <form class="card hero" @submit.prevent="start">
      <label class="label" for="url" style="display:block;margin-bottom:8px">Website to save</label>
      <div class="url-row">
        <div class="url-input" :class="{ invalid: errors.url }">
          <Icon name="globe" />
          <input id="url" v-model.trim="form.url" placeholder="https://docs.example.com/"
                 autocomplete="off" spellcheck="false" autofocus />
        </div>
        <button class="btn btn-primary btn-lg" type="submit" :disabled="submitting">
          Start crawl <Icon name="arrowRight" />
        </button>
      </div>
      <p v-if="errors.url" class="error-text" style="margin-top:8px">{{ errors.url }}</p>
      <p v-else class="hint" style="margin-top:8px">
        Same-site pages are saved with their CSS, images and fonts. Run again to resume.
      </p>
    </form>

    <section class="card">
      <div class="card-title"><Icon name="sparkle" /> Capture quality</div>
      <div class="segmented" role="radiogroup">
        <button v-for="name in [...PRESET_NAMES, 'Custom']" :key="name" type="button"
                role="radio" :aria-checked="form.preset === name"
                :class="{ active: form.preset === name }" @click="choosePreset(name)">
          {{ name }}
        </button>
      </div>
      <p class="preset-desc">{{ presetDescription }}</p>
    </section>

    <div class="grid-2">
      <section class="card">
        <div class="card-title"><Icon name="folder" /> Save to</div>
        <div class="field">
          <div class="input-group">
            <input class="input mono" :class="{ invalid: errors.output_dir }"
                   v-model.trim="form.output_dir" spellcheck="false"
                   @change="refreshLibrary" style="font-size:12.5px" />
            <button v-if="store.config?.can_pick_folder" type="button" class="btn"
                    @click="browse">Browse…</button>
          </div>
          <p v-if="errors.output_dir" class="error-text">{{ errors.output_dir }}</p>
          <p v-else class="hint">Each site gets its own folder inside this one.</p>
        </div>
        <div class="field">
          <label class="label" for="excl">Skip paths</label>
          <textarea id="excl" class="textarea" v-model="form.exclude_patterns" rows="3"
                    placeholder="/blog/*&#10;/forum/*" spellcheck="false"></textarea>
          <p class="hint">One pattern per line.</p>
        </div>
      </section>

      <section class="card">
        <div class="card-title"><Icon name="gauge" /> Speed</div>
        <div class="field-row">
          <div class="field">
            <label class="label" for="pp">Parallel pages</label>
            <select id="pp" class="select" v-model.number="form.concurrency">
              <option v-for="n in store.config?.page_concurrency_choices || []" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <div class="field">
            <label class="label" for="pa">Parallel assets</label>
            <select id="pa" class="select" v-model.number="form.asset_concurrency">
              <option v-for="n in store.config?.asset_concurrency_choices || []" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label class="label" for="mp">Page limit</label>
          <input id="mp" class="input" :class="{ invalid: errors.max_pages }" type="number"
                 min="1" v-model="form.max_pages" placeholder="No limit" />
          <p v-if="errors.max_pages" class="error-text">{{ errors.max_pages }}</p>
        </div>
        <label class="switch">
          <span>
            <span style="font-weight:550">Re-fetch saved pages</span><br />
            <span class="hint">Otherwise pages already on disk are skipped.</span>
          </span>
          <input type="checkbox" v-model="form.force" />
          <span class="track"></span>
        </label>
      </section>
    </div>

    <details class="card disclosure" :open="advancedOpen" @toggle="advancedOpen = $event.target.open">
      <summary><Icon name="sliders" /> Advanced timings
        <Icon name="chevronDown" class="chev" />
      </summary>
      <div class="body">
        <div class="timings">
          <div class="field" v-for="f in TIMING_FIELDS" :key="f.key">
            <label class="label" :for="f.key">{{ f.label }}</label>
            <div class="unit-input">
              <input :id="f.key" class="input" :class="{ invalid: errors[f.key] }" type="number"
                     min="0" v-model.number="form[f.key]" @input="onTimingInput" />
              <span>{{ f.unit }}</span>
            </div>
            <p v-if="errors[f.key]" class="error-text">{{ errors[f.key] }}</p>
          </div>
        </div>
        <p class="hint" style="margin-top:12px">Changing a timing switches the preset to Custom.</p>
      </div>
    </details>
  </div>`,
};

// -- Run view ------------------------------------------------------------------

const RunView = {
  components: { Icon },
  setup() {
    const now = ref(Date.now() / 1000);
    const logOpen = ref(false);
    const logEl = ref(null);
    let timer = null;
    onMounted(() => {
      timer = setInterval(() => (now.value = Date.now() / 1000), 1000);
    });
    onBeforeUnmount(() => clearInterval(timer));

    const s = computed(() => store.session);
    const p = computed(() => store.session.progress || {});
    const active = computed(() => ACTIVE_STATES.has(s.value.state));
    const elapsed = computed(() => {
      const start = s.value.started_at;
      if (!start) return "0:00";
      return formatDuration((s.value.finished_at || now.value) - start);
    });
    const errorCount = computed(() => (p.value.failed ?? p.value.errors) || 0);

    function scrollLog() {
      nextTick(() => {
        const el = logEl.value;
        if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 80) {
          el.scrollTop = el.scrollHeight;
        }
      });
    }
    watch(() => store.log.length, scrollLog);
    watch(logOpen, (open) =>
      open && nextTick(() => logEl.value && (logEl.value.scrollTop = logEl.value.scrollHeight)),
    );
    watch(
      () => s.value.state,
      (state) => {
        if (state === "failed") logOpen.value = true;
      },
      { immediate: true },
    );

    function lineClass(line) {
      if (line.startsWith("$ ")) return "l-cmd";
      if (line.startsWith("[Folio]")) return "l-note";
      if (/^(Skipped|Failed|Warning|Crawl failed|Traceback)/.test(line)) return "l-bad";
      if (/^(Rate limited|Retrying|Resuming)/.test(line)) return "l-warn";
      if (/^Crawl complete/.test(line)) return "l-ok";
      return "";
    }

    async function cont() {
      try {
        await api("/api/crawl/continue", {});
      } catch (err) {
        toast(err.message, "error");
      }
    }
    async function stop() {
      try {
        await api("/api/crawl/stop", {});
      } catch (err) {
        toast(err.message, "error");
      }
    }
    function newCrawl() {
      store.showForm = true;
    }

    return {
      store,
      s,
      p,
      active,
      elapsed,
      errorCount,
      logOpen,
      logEl,
      lineClass,
      cont,
      stop,
      newCrawl,
      openSite,
      avatarStyle,
      avatarLetter,
      STATE_LABELS,
    };
  },
  template: `
  <div class="page">
    <div class="run-head">
      <div class="avatar" :style="avatarStyle(s.host)">{{ avatarLetter(s.host) }}</div>
      <div class="titles">
        <h1>{{ s.host }}</h1>
        <span class="pill" :class="s.state"><span class="dot" :class="s.state"></span>{{ STATE_LABELS[s.state] }}</span>
      </div>
      <div class="actions">
        <button v-if="active" class="btn btn-danger" @click="stop" :disabled="s.state === 'stopping'">
          <Icon name="stop" /> Stop
        </button>
        <template v-else>
          <button class="btn" @click="newCrawl"><Icon name="plus" /> New crawl</button>
          <button v-if="s.state === 'finished'" class="btn btn-primary"
                  @click="openSite(s.host, s.output_dir)"><Icon name="external" /> Open site</button>
        </template>
      </div>
    </div>

    <div class="progress"
         :class="{ indeterminate: active, done: s.state === 'finished', bad: s.state === 'failed' || s.state === 'stopped' }">
      <div class="bar"></div>
    </div>

    <div v-if="s.state === 'waiting_login'" class="banner">
      <div class="icon-wrap"><Icon name="key" /></div>
      <div class="text">
        <h3>Sign in if you need to</h3>
        <p>A browser window has opened. Log in there, then come back and continue.</p>
      </div>
      <button class="btn btn-gold" @click="cont">I'm logged in, continue</button>
    </div>

    <div v-else-if="s.state === 'finished'" class="banner success">
      <div class="icon-wrap"><Icon name="check" /></div>
      <div class="text">
        <h3>Saved {{ p.saved ?? 0 }} new page{{ p.saved === 1 ? '' : 's' }}</h3>
        <p>
          {{ p.skipped_existing || 0 }} already on disk<span v-if="p.failed">, {{ p.failed }} failed — run again to retry them</span>.
          Took {{ elapsed }}.
        </p>
      </div>
    </div>

    <div v-else-if="s.state === 'failed' || s.state === 'stopped'" class="banner bad">
      <div class="icon-wrap"><Icon :name="s.state === 'stopped' ? 'stop' : 'alert'" /></div>
      <div class="text">
        <h3>{{ s.state === 'stopped' ? 'Crawl stopped' : 'Crawl failed' }}</h3>
        <p v-if="s.state === 'stopped'">Pages saved so far are kept. Start the same crawl again to resume.</p>
        <p v-else>Exited with code {{ s.return_code }}. Check the log below for details.</p>
      </div>
    </div>

    <div class="stats">
      <div class="card stat">
        <div class="label"><Icon name="file" /> Pages fetched</div>
        <div class="value">{{ p.fetched || 0 }}</div>
      </div>
      <div class="card stat">
        <div class="label"><Icon name="skip" /> Already saved</div>
        <div class="value">{{ p.skipped_existing || 0 }}</div>
      </div>
      <div class="card stat" :class="{ bad: errorCount > 0 }">
        <div class="label"><Icon name="alert" /> {{ p.failed != null ? 'Failed' : 'Errors' }}</div>
        <div class="value">{{ errorCount }}</div>
      </div>
      <div class="card stat">
        <div class="label"><Icon name="clock" /> Elapsed</div>
        <div class="value">{{ elapsed }}</div>
      </div>
    </div>

    <div v-if="active && p.current_url" class="card now">
      <span class="label">Now fetching</span>
      <span class="url" :title="p.current_url">{{ p.current_url }}</span>
    </div>
    <div v-if="p.rate_limited" class="hint">Rate limited {{ p.rate_limited }}× — Folio is backing off automatically.</div>

    <section class="card log-card">
      <div class="log-head" :class="{ open: logOpen }" @click="logOpen = !logOpen">
        <Icon name="terminal" /> Activity log <span class="count">{{ store.log.length }} line{{ store.log.length === 1 ? '' : 's' }}</span>
        <Icon name="chevronDown" class="chev" />
      </div>
      <div v-if="logOpen" class="log" ref="logEl"><div v-for="(line, i) in store.log" :key="i" :class="lineClass(line)">{{ line }}</div></div>
    </section>
  </div>`,
};

// -- Library -------------------------------------------------------------------

const LibraryView = {
  components: { Icon },
  setup() {
    const query = ref("");
    const filtered = computed(() => {
      const q = query.value.trim().toLowerCase();
      return q ? store.sites.filter((s) => s.host.toLowerCase().includes(q)) : store.sites;
    });
    function recrawl(host) {
      const local = /^(localhost|127\.)/.test(host);
      store.form.url = `${local ? "http" : "https"}://${host}/`;
      store.showForm = !ACTIVE_STATES.has(store.session.state);
      store.view = "crawl";
    }
    function startNew() {
      store.view = "crawl";
      store.showForm = !ACTIVE_STATES.has(store.session.state);
    }
    return {
      store,
      query,
      filtered,
      recrawl,
      startNew,
      refreshLibrary,
      openSite,
      avatarStyle,
      avatarLetter,
      relativeTime,
      shortPath,
    };
  },
  template: `
  <div class="page">
    <header class="page-header">
      <div class="heading">
        <h1>Library</h1>
        <p>{{ store.sites.length }} saved site{{ store.sites.length === 1 ? '' : 's' }} in
          <span class="path" :title="store.libraryDir">{{ shortPath(store.libraryDir) }}</span></p>
      </div>
      <div class="toolbar">
        <label class="search"><Icon name="search" />
          <input v-model="query" placeholder="Filter sites" spellcheck="false" />
        </label>
        <button class="btn btn-icon" title="Refresh" @click="refreshLibrary"
                :disabled="store.libraryLoading"><Icon name="refresh" /></button>
      </div>
    </header>

    <div v-if="filtered.length" class="sites">
      <article v-for="site in filtered" :key="site.host" class="card site">
        <div class="site-top">
          <div class="avatar" :style="avatarStyle(site.host)">{{ avatarLetter(site.host) }}</div>
          <div style="min-width:0">
            <div class="site-host" :title="site.host">{{ site.host }}</div>
            <div class="site-meta">{{ site.page_count.toLocaleString() }} page{{ site.page_count === 1 ? '' : 's' }} · {{ relativeTime(site.modified_at) }}</div>
          </div>
        </div>
        <div class="site-actions">
          <button class="btn btn-primary" @click="openSite(site.host)"><Icon name="external" /> Open</button>
          <button class="btn" @click="recrawl(site.host)"><Icon name="rotate" /> Update</button>
        </div>
      </article>
    </div>

    <div v-else-if="store.sites.length" class="card empty">
      <h3>No matches</h3>
      <p>No saved site matches "{{ query }}".</p>
    </div>

    <div v-else class="card empty">
      <div class="icon-wrap"><Icon name="library" /></div>
      <h3>No saved sites yet</h3>
      <p>Sites you crawl show up here, ready to browse offline.</p>
      <button class="btn btn-primary" @click="startNew"><Icon name="plus" /> Start a crawl</button>
    </div>
  </div>`,
};

// -- Root ----------------------------------------------------------------------

const App = {
  components: { Icon, CrawlForm, RunView, LibraryView },
  setup() {
    const s = computed(() => store.session);
    const active = computed(() => ACTIVE_STATES.has(s.value.state));
    const showRun = computed(
      () => store.view === "crawl" && (active.value || (!store.showForm && s.value.state !== "idle")),
    );

    function goCrawl() {
      store.view = "crawl";
    }
    function goStatus() {
      store.view = "crawl";
      if (s.value.state !== "idle") store.showForm = false;
    }

    onMounted(async () => {
      loadSavedForm();
      try {
        store.config = await api("/api/config");
        if (!store.form.output_dir) store.form.output_dir = store.config.output_dir;
        if (store.form.preset !== "Custom" && store.config.presets[store.form.preset]) {
          Object.assign(store.form, store.config.presets[store.form.preset]);
        }
        const state = await api("/api/state");
        store.log = state.log || [];
        delete state.log;
        store.session = state;
        if (state.state !== "idle") store.showForm = false;
      } catch (err) {
        toast(err.message, "error");
      }
      connectEvents();
      refreshLibrary();
    });

    watch(
      () => store.form,
      () => saveForm(),
      { deep: true },
    );

    return { store, s, active, showRun, goCrawl, goStatus, STATE_LABELS, shortPath };
  },
  template: `
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <img src="/static/folio.png" alt="" />
        <span class="brand-name">Folio</span>
      </div>
      <button class="nav-item" :class="{ active: store.view === 'crawl' }" @click="goCrawl">
        <Icon name="plus" /> Crawl
      </button>
      <button class="nav-item" :class="{ active: store.view === 'library' }" @click="store.view = 'library'">
        <Icon name="library" /> Library <span class="nav-badge">{{ store.sites.length || '' }}</span>
      </button>
      <div class="sidebar-footer">
        <button class="status-card" @click="goStatus">
          <span class="dot" :class="s.state"></span>
          <span style="min-width:0">
            <span class="label">{{ STATE_LABELS[s.state] }}</span>
            <div class="sub" v-if="s.host">{{ s.host }}</div>
            <div class="sub" v-else>No crawl running</div>
          </span>
        </button>
        <div class="folder-hint" :title="store.form.output_dir">Saving to {{ shortPath(store.form.output_dir) }}</div>
      </div>
    </aside>
    <main class="main">
      <LibraryView v-if="store.view === 'library'" />
      <RunView v-else-if="showRun" />
      <CrawlForm v-else />
    </main>
    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">
        <Icon :name="t.kind === 'error' ? 'alert' : 'check'" /> {{ t.message }}
      </div>
    </div>
  </div>`,
};

createApp(App).mount("#app");
