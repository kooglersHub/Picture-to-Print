const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

function application() {
  const elements = new Map();
  const element = () => ({
    hidden: false,
    textContent: "",
    value: "",
    children: [],
    attributes: {},
    addEventListener() {},
    replaceChildren(...items) {
      this.children = items;
    },
    append(...items) {
      this.children.push(...items);
    },
    setAttribute(key, value) {
      this.attributes[key] = value;
    },
    getAttribute(key) {
      return this.attributes[key];
    },
    removeAttribute(key) {
      delete this.attributes[key];
    },
  });
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, element());
        return elements.get(id);
      },
      createElement: element,
      createTextNode: String,
    },
    FormData,
    fetch() {
      return new Promise(() => {});
    },
    setInterval() {},
    URLSearchParams,
    location: { hash: "" },
  });
  vm.runInContext(
    fs
      .readFileSync(
        path.join(__dirname, "../picture_to_print/static/app.js"),
        "utf8",
      )
      .replace("initialize();", ""),
    context,
  );
  return { context, elements, run: (code) => vm.runInContext(code, context) };
}

test("stage default prefers export, then raw, then latest available mesh", () => {
  const { run } = application();
  assert.equal(
    run(
      "defaultStageId([{id:'raw',kind:'mesh',status:'available'},{id:'exported',kind:'mesh',status:'available'}])",
    ),
    "exported",
  );
  assert.equal(
    run(
      "defaultStageId([{id:'raw',kind:'mesh',status:'available'},{id:'exported',kind:'mesh',status:'missing'}])",
    ),
    "raw",
  );
  assert.equal(
    run(
      "defaultStageId([{id:'prepared',kind:'mesh',status:'available'},{id:'capped',kind:'mesh',status:'available'}])",
    ),
    "capped",
  );
});

test("stage backfill uses the selected job settings", () => {
  const { run } = application();
  const data = run(
    "repairSettings({settings:{size_mm:150,voxel_mm:0.2,backend:'blender'}})",
  );
  assert.deepEqual(Object.fromEntries(data), {
    size_mm: "150",
    voxel_mm: "0.2",
    backend: "blender",
  });
});

test("stale stage requests cannot replace newly selected job data", async () => {
  const app = application();
  app.run(
    "selectedJob = {id:'old'}; let completeStages; api = () => new Promise(resolve => completeStages = resolve); globalThis.request = loadStages(selectedJob); selectedJob = {id:'new'};",
  );
  app.run(
    "completeStages({stages:[{id:'raw',kind:'mesh',status:'available'}],size_mm:100});",
  );
  await app.context.request;
  assert.equal(app.run("stageData"), null);
});

test("polling retains selected diagnostic stage and camera", async () => {
  const app = application();
  app.run(
    "selectedJob = {id:'same',settings:{size_mm:100},status:'ready'}; selectedStageId = 'raw'; stageData = {stages:[]}; cameraJobId = 'same'; document.getElementById('viewer').setAttribute('camera-orbit','user-camera'); api = async () => ({size_mm:100,stages:[{id:'raw',kind:'mesh',status:'available',preview_url:'/raw.glb',metrics:{triangles:12}},{id:'exported',kind:'mesh',status:'available',preview_url:'/final.glb'}]}); globalThis.request = loadStages(selectedJob);",
  );
  await app.context.request;
  assert.equal(app.run("selectedStageId"), "raw");
  assert.equal(app.elements.get("viewer").attributes.src, "/raw.glb");
  assert.equal(
    app.elements.get("viewer").attributes["camera-orbit"],
    "user-camera",
  );
});

test("missing images hide previous preview and download instead of reconstructing them", () => {
  const app = application();
  app.run(
    "stageData = {stages:[{id:'foreground',label:'Freistellung',kind:'image',status:'missing'}]}; selectedStageId = 'foreground'; renderStage();",
  );
  assert.equal(app.elements.get("stage-image").hidden, true);
  assert.equal(app.elements.get("viewer").hidden, true);
  assert.equal(app.elements.get("stage-download").hidden, true);
  assert.match(
    app.elements.get("stage-description").textContent,
    /nicht gespeichert/,
  );
});

test("stage navigation stops at endpoints and keeps camera through changes", () => {
  const app = application();
  app.run(
    "stageData = {stages:[{id:'input',kind:'image',status:'available',preview_url:'/input.png'},{id:'raw',kind:'mesh',status:'available',preview_url:'/raw.glb'},{id:'exported',kind:'mesh',status:'available',preview_url:'/final.glb'}]}; selectedStageId = 'input'; document.getElementById('viewer').setAttribute('camera-orbit','user-camera'); renderStage(); moveStage(-1);",
  );
  assert.equal(app.run("selectedStageId"), "input");
  assert.equal(app.elements.get("stage-previous").disabled, true);
  assert.equal(app.elements.get("stage-next").disabled, false);
  assert.equal(app.elements.get("stage-counter").textContent, "1 / 3");
  app.run("moveStage(1);");
  assert.equal(app.run("selectedStageId"), "raw");
  assert.equal(app.elements.get("viewer").attributes.src, "/raw.glb");
  assert.equal(app.elements.get("stage-select").value, "raw");
  app.run("moveStage(1); moveStage(1);");
  assert.equal(app.run("selectedStageId"), "exported");
  assert.equal(app.elements.get("stage-next").disabled, true);
  assert.equal(app.elements.get("stage-previous").disabled, false);
  assert.equal(app.elements.get("stage-counter").textContent, "3 / 3");
  assert.equal(
    app.elements.get("viewer").attributes["camera-orbit"],
    "user-camera",
  );
});

test("empty stage navigation disables both directions", () => {
  const app = application();
  app.run("stageData = {stages:[]}; renderStage(); moveStage(1);");
  assert.equal(app.run("selectedStageId"), null);
  assert.equal(app.elements.get("stage-previous").disabled, true);
  assert.equal(app.elements.get("stage-next").disabled, true);
  assert.equal(app.elements.get("stage-counter").textContent, "0 / 0");
});
