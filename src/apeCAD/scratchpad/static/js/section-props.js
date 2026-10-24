// Interactive Properties dock editors for section-mode entities (ADR 0024).
import { S } from "./state.js";
import { t } from "./strings.js";
import { api } from "./api.js";
import { brepKind, pointById } from "./brep.js";
import { refuse, setHint } from "./cmdline.js";
import { formatMm } from "./prefs.js";
import { refreshFrom } from "./render.js";
import { SECTION_KINDS } from "./section.js";

export const DESIGNATIONS = ["Ø8", "Ø10", "Ø12", "Ø14", "Ø16", "Ø18", "Ø20", "Ø22", "Ø25", "Ø28", "Ø32"];

function makeRow(container, labelText) {
  const wrap = document.createElement("div");
  wrap.className = "prop";
  const dt = document.createElement("dt");
  dt.textContent = labelText;
  const dd = document.createElement("dd");
  wrap.append(dt, dd);
  container.append(wrap);
  return dd;
}

function addTextRow(container, labelText, valueText) {
  const dd = makeRow(container, labelText);
  dd.textContent = valueText;
}

function addSelectRow(container, labelText, options, current, onChange) {
  const dd = makeRow(container, labelText);
  const select = document.createElement("select");
  for (const [val, text] of options) {
    const opt = document.createElement("option");
    opt.value = String(val);
    opt.textContent = text;
    if (String(val) === String(current)) opt.selected = true;
    select.append(opt);
  }
  select.addEventListener("change", () => onChange(select.value));
  dd.append(select);
}

function addNumberRow(container, labelText, current, min, step, onChange) {
  const dd = makeRow(container, labelText);
  const input = document.createElement("input");
  input.type = "number";
  input.min = String(min);
  input.step = String(step);
  input.value = String(current);
  input.addEventListener("change", () => {
    const val = Number(input.value);
    if (Number.isFinite(val) && val >= min) onChange(val);
  });
  dd.append(input);
}

function addInputRow(container, labelText, current, onChange) {
  const dd = makeRow(container, labelText);
  const input = document.createElement("input");
  input.type = "text";
  input.value = current || "";
  input.addEventListener("change", () => onChange(input.value.trim()));
  dd.append(input);
}

async function postPropOp(body, field) {
  try {
    await refreshFrom(await api("/api/op", "POST", body));
    setHint(t("done.propUpdated", { field }));
  } catch (error) {
    refuse(error);
  }
}

export function renderSectionProps(propBody, rows) {
  const selected = rows.filter((row) => S.selectedIds.has(row.id));
  if (selected.length === 0) return false;
  if (selected.length > 1) {
    if (selected.every((row) => row.kind === "Bar")) {
      propBody.replaceChildren();
      addTextRow(propBody, "Selection", `${selected.length} bars`);
      const firstDia = selected[0].item.designation;
      addSelectRow(
        propBody,
        "Bar",
        DESIGNATIONS.map((d) => [d, d]),
        firstDia,
        (designation) => postPropOp({
          op: "SetBarSize",
          entity_ids: selected.map((r) => r.id),
          designation,
        }, "bar size"),
      );
      return true;
    }
    if (selected.every((row) => row.kind === "Hoop" || row.kind === "Crosstie")) {
      propBody.replaceChildren();
      addTextRow(propBody, "Selection", `${selected.length} ties`);
      const first = selected[0].item;
      addSelectRow(
        propBody,
        "Tie",
        DESIGNATIONS.map((d) => [d, d]),
        first.designation,
        (designation) => postPropOp({
          op: "SetTransverse",
          entity_ids: selected.map((r) => r.id),
          designation,
        }, "tie size"),
      );
      addNumberRow(propBody, "Spacing mm", first.spacing_mm, 10, 10, (spacing_mm) => postPropOp({
        op: "SetTransverse",
        entity_ids: selected.map((r) => r.id),
        spacing_mm,
      }, "tie spacing"));
      return true;
    }
    return false;
  }

  const row = selected[0];
  if (!SECTION_KINDS.includes(row.kind)) return false;
  const item = row.item;
  propBody.replaceChildren();
  addTextRow(propBody, "Type", brepKind(row.kind));
  addInputRow(propBody, "Label", item.label || "", (val) => postPropOp({
    op: "SetLabel",
    entity_id: row.id,
    label: val || null,
  }, "label"));

  if (row.kind === "ConcreteFace") {
    addInputRow(propBody, "Material", item.material, (val) => {
      if (val) postPropOp({ op: "SetMaterial", entity_ids: [row.id], material: val }, "material");
    });
    addTextRow(propBody, "Vertices", String(item.point_ids.length));
    return true;
  }

  if (row.kind === "Bar") {
    addSelectRow(
      propBody,
      "Bar",
      DESIGNATIONS.map((d) => [d, d]),
      item.designation,
      (designation) => postPropOp({ op: "SetBarSize", entity_ids: [row.id], designation }, "bar size"),
    );
    addTextRow(propBody, "Diameter", formatMm(item.diameter_mm));
    const centre = pointById(item.point_id);
    if (centre) {
      addTextRow(propBody, "X", formatMm(centre.x_mm));
      addTextRow(propBody, "Y", formatMm(centre.y_mm));
    }
    return true;
  }

  if (row.kind === "Hoop" || row.kind === "Crosstie") {
    addSelectRow(
      propBody,
      "Tie",
      DESIGNATIONS.map((d) => [d, d]),
      item.designation,
      (designation) => postPropOp({ op: "SetTransverse", entity_ids: [row.id], designation }, "tie size"),
    );
    addNumberRow(propBody, "Spacing mm", item.spacing_mm, 10, 10, (spacing_mm) => postPropOp({
      op: "SetTransverse",
      entity_ids: [row.id],
      spacing_mm,
    }, "tie spacing"));
    if (row.kind === "Crosstie") {
      addSelectRow(
        propBody,
        "Hooks",
        [["135-135", "135-135"], ["135-90", "135-90"]],
        item.hooks,
        (hooks) => postPropOp({ op: "SetTransverse", entity_ids: [row.id], hooks }, "hooks"),
      );
    } else {
      addTextRow(propBody, "Hooks", item.hooks);
      addTextRow(propBody, "Bars", String(item.bar_ids.length));
    }
    return true;
  }

  if (row.kind === "WallLeg") {
    addTextRow(propBody, "Thickness", formatMm(item.thickness_mm));
    const steel = item.horizontal;
    const curtains = steel ? steel.curtains : S.sec.curtains || 2;
    const desig = steel ? steel.designation : S.sec.barDia;
    const spacing = steel ? steel.spacing_mm : S.sec.spacingMm;
    const commitLeg = (nextCurtains, nextDesig, nextSpacing) => {
      postPropOp({
        op: "SetLegReinforcement",
        leg_id: row.id,
        designation: nextDesig,
        spacing_mm: nextSpacing,
        curtains: Math.max(1, nextCurtains),
      }, "leg reinforcement");
    };
    addSelectRow(
      propBody,
      "Curtains",
      [[1, "1"], [2, "2"], [3, "3"], [4, "4"]],
      curtains,
      (val) => commitLeg(Number(val), desig, spacing),
    );
    addSelectRow(
      propBody,
      "Horizontal",
      DESIGNATIONS.map((d) => [d, d]),
      desig,
      (val) => commitLeg(curtains, val, spacing),
    );
    addNumberRow(propBody, "Spacing mm", spacing, 25, 25, (val) => commitLeg(curtains, desig, val));
    return true;
  }

  if (row.kind === "CoverGuide") {
    const commitCover = (cover_mm, tie_diameter_mm, bar_diameter_mm) => postPropOp({
      op: "SetCover",
      face_id: item.face_id,
      cover_mm,
      tie_diameter_mm,
      bar_diameter_mm,
    }, "cover guide");
    addNumberRow(propBody, "Cover mm", item.cover_mm, 1, 5, (val) => commitCover(
      val, item.tie_diameter_mm, item.bar_diameter_mm,
    ));
    addNumberRow(propBody, "Tie mm", item.tie_diameter_mm, 0, 2, (val) => commitCover(
      item.cover_mm, val, item.bar_diameter_mm,
    ));
    addNumberRow(propBody, "Bar mm", item.bar_diameter_mm, 6, 2, (val) => commitCover(
      item.cover_mm, item.tie_diameter_mm, val,
    ));
    return true;
  }

  return false;
}
