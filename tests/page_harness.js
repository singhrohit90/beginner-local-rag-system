"use strict";
// Runs the chat page's real script in node against a small fake DOM and a stubbed fetch, then prints one JSON
// line with what the page did. Used by tests/test_page_conversation.py; no browser, model or network is needed.
//
//   node tests/page_harness.js <scenario> '<json of the server strings>'   (the page script on stdin)
//
// The fake DOM throws on any HTML insertion, so a scenario fails if the page ever builds markup from text.
const vm = require("node:vm");

const A_ID = "a".repeat(32), B_ID = "b".repeat(32), C_ID = "c".repeat(32), D_ID = "d".repeat(32);
const DETAIL_HINT = "Click an answer to see its passages and stage timings.";

function textNode(data) { return { nodeType: 3, data: String(data), parentNode: null }; }

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.id = ""; this.children = []; this.parentNode = null; this.className = "";
    this.value = ""; this.disabled = false; this.hidden = false; this.checked = false;
    this.type = ""; this.title = ""; this.placeholder = ""; this.files = [];
    this.onclick = null; this.onsubmit = null; this.onchange = null; this.onkeydown = null;
    const self = this;
    this.classList = {
      add(name) { if (!self.classList.contains(name)) self.className = (self.className + " " + name).trim(); },
      remove(name) { self.className = self.className.split(/\s+/).filter((c) => c && c !== name).join(" "); },
      contains(name) { return self.className.split(/\s+/).includes(name); },
    };
  }
  adopt(kid) {
    const node = typeof kid === "string" || typeof kid === "number" ? textNode(kid) : kid;
    if (node.parentNode) node.parentNode.children = node.parentNode.children.filter((c) => c !== node);
    node.parentNode = this;
    return node;
  }
  append(...kids) { for (const kid of kids) this.children.push(this.adopt(kid)); }
  prepend(...kids) { const nodes = kids.map((k) => this.adopt(k)); this.children = nodes.concat(this.children); }
  replaceChildren(...kids) {
    for (const c of this.children) c.parentNode = null;
    this.children = [];
    this.append(...kids);
  }
  before(...kids) {
    const parent = this.parentNode;
    if (!parent) return;
    const nodes = kids.map((k) => parent.adopt(k));
    const at = parent.children.indexOf(this);
    parent.children.splice(at, 0, ...nodes);
  }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((c) => c !== this); this.parentNode = null; }
  click() { if (this.onclick) return this.onclick({ stopPropagation() {}, preventDefault() {} }); }
  scrollIntoView() {}
  focus() {}
  requestSubmit() { if (this.onsubmit) return this.onsubmit({ preventDefault() {} }); }
  get textContent() { return textOf(this); }
  set textContent(value) { this.replaceChildren(); if (value !== "" && value != null) this.append(String(value)); }
  // Markup insertion is what the page must never do: fail loudly.
  get innerHTML() { throw new Error("innerHTML read"); }
  set innerHTML(_) { throw new Error("innerHTML assigned"); }
  get outerHTML() { throw new Error("outerHTML read"); }
  set outerHTML(_) { throw new Error("outerHTML assigned"); }
  insertAdjacentHTML() { throw new Error("insertAdjacentHTML called"); }
}

function textOf(node) {
  if (node.nodeType === 3) return node.data;
  return node.children.map(textOf).join("");
}

function tagsOf(node) {
  if (node.nodeType === 3) return [];
  return [node.tagName].concat(...node.children.map(tagsOf));
}

function makeDocument() {
  const byId = new Map();
  const defaults = {
    scope: (e) => { e.value = "all"; }, mode: (e) => { e.value = "content"; }, config: (e) => { e.value = "weighted"; },
    question: (e) => { e.value = ""; }, file: (e) => { e.files = []; },
    detail: (e) => { e.append(DETAIL_HINT); }, starting: (e) => { e.append("Loading the models."); },
  };
  return {
    getElementById(id) {
      if (!byId.has(id)) {
        const e = new FakeElement("div"); e.id = id;
        if (defaults[id]) defaults[id](e);
        byId.set(id, e);
      }
      return byId.get(id);
    },
    createElement(tag) { return new FakeElement(tag); },
    createTextNode(data) { return textNode(data); },
    querySelectorAll() { return []; },
  };
}

let queryCounter = 0;
function finalEvent(id, extra = {}) {
  queryCounter += 1;
  return Object.assign({
    answer: "Copies live on several nodes [S1].", citations: ["S1"], passages: [], stages: [], blocked: [],
    skipped_by_scanner: [], documents: [{ id: "d1", name: "a.pdf" }], abstained: false, replace: false,
    llm: "fake", seconds: 0.1, query_id: "q-" + queryCounter, conversation_id: id, turn: 1, kind: "answer",
    rewrite: { status: "off", reason: null, rewritten_question: null },
  }, extra);
}

function frame(final) { return new TextEncoder().encode("event: final\ndata: " + JSON.stringify(final) + "\n\n"); }

function jsonResponse(status, value) {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function makeFetch(state) {
  return async function fetch(url, options = {}) {
    const method = options.method || "GET";
    let body = options.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch (_) { /* keep the text */ } }
    state.calls.push({ url, method, body, signal: options.signal || null });
    if (url === "/v1/health") return jsonResponse(200, { ready: true, error: null });
    if (url === "/v1/status") {
      return jsonResponse(200, { models_loaded: true, llm: { ok: true, name: "fake", detail: "ok" },
                                 search: { ok: true, detail: "ok" }, error: null });
    }
    if (url === "/v1/documents" && method === "GET") return jsonResponse(200, state.docs);
    if (url.startsWith("/v1/documents/") && method === "DELETE") {
      const id = url.slice("/v1/documents/".length);
      state.docs = state.docs.filter((d) => d.id !== id);
      return new Response(null, { status: 204 });
    }
    if (url === "/v1/ask/stream" && method === "POST") {
      if (!state.replies.length) throw new Error("no reply queued for /v1/ask/stream");
      const reply = state.replies.shift();
      if (reply.status) return jsonResponse(reply.status, reply.json);
      if (reply.final) return new Response(frame(reply.final), { status: 200, headers: { "Content-Type": "text/event-stream" } });
      if (reply.hold) {
        // The stream stays open until the scenario delivers a frame; an abort does not close it, so a late
        // final really reaches the page and the page itself must ignore it.
        const stream = new ReadableStream({ start(controller) { state.held = controller; } });
        return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
      }
      throw new Error("bad reply " + JSON.stringify(reply));
    }
    if (url === "/v1/ask-about" && method === "POST") throw new Error("ask-about is not used by these scenarios");
    throw new Error("unexpected request " + method + " " + url);
  };
}

async function waitFor(cond, label) {
  const until = Date.now() + 30000;
  while (!cond()) {
    if (Date.now() > until) throw new Error("timeout: " + label);
    await new Promise((r) => setImmediate(r));
  }
}

class FakeFormData { constructor() { this.parts = []; } append(name, value) { this.parts.push([name, value]); } }

function docRecord(id, name) {
  return { id, name, state: "ready", chunks: 3, chunker: "recursive", flagged_chunks: 0, error: null, stage: null };
}

async function boot(script) {
  const state = { calls: [], replies: [], held: null, docs: [docRecord("d1", "a.pdf"), docRecord("d2", "b.pdf")] };
  const document = makeDocument();
  // The page's timers never fire, so polling and status checks cannot race a scenario.
  const globals = {
    document, fetch: makeFetch(state), setTimeout: () => 0, clearTimeout: () => {},
    Response, TextDecoder, TextEncoder, AbortController, ReadableStream, FormData: FakeFormData, console,
  };
  const ctx = vm.createContext(globals);
  vm.runInContext(script, ctx);
  await waitFor(() => vm.runInContext("ready && docs.length === 2", ctx), "page ready");
  return { ctx, state, $: (id) => document.getElementById(id) };
}

async function ask(page, question) {
  page.$("question").value = question;
  await page.$("ask").onsubmit({ preventDefault() {} });
}

function idOf(page) { return vm.runInContext("conversationId", page.ctx); }

function observe(page) {
  const asks = page.state.calls.filter((c) => c.url === "/v1/ask/stream");
  return {
    conversationId: idOf(page),
    askBodies: asks.map((c) => c.body),
    askAborted: asks.map((c) => Boolean(c.signal && c.signal.aborted)),
    logText: textOf(page.$("log")), errorText: textOf(page.$("error")), detailText: textOf(page.$("detail")),
    logTags: tagsOf(page.$("log")).slice(1), sendDisabled: page.$("send").disabled,
  };
}

const SCENARIOS = {
  async follow_up(page) {
    page.state.replies.push({ final: finalEvent(A_ID) }, { final: finalEvent(A_ID, { turn: 2 }) });
    await ask(page, "How does replication survive a node failure?");
    await ask(page, "and what about its drawbacks?");
    return observe(page);
  },
};

async function main() {
  const scenario = process.argv[2];
  let result;
  try {
    const strings = JSON.parse(process.argv[3] || "{}");
    let script = "";
    process.stdin.setEncoding("utf8");
    for await (const chunk of process.stdin) script += chunk;
    if (!Object.prototype.hasOwnProperty.call(SCENARIOS, scenario)) throw new Error("unknown scenario " + scenario);
    const page = await boot(script);
    result = { scenario, ok: true, obs: await SCENARIOS[scenario](page, strings) };
  } catch (err) {
    result = { scenario, ok: false, error: String(err && err.stack || err) };
  }
  process.stdout.write(JSON.stringify(result) + "\n");
}

main();
