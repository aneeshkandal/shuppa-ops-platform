"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import DataTable from "../../../components/DataTable";
import { adminApi } from "../../../lib/api";
import CustomDropdown from "../../../components/CustomDropdown";

type ParsedRow = Record<string, any>;
type UploadType = "products" | "suppliers" | "locations";

type TypeConfig = {
  label: string;
  template: string;
  required: string[];
  help: string;
  parseRow: (raw: Record<string, string>) => ParsedRow;
  previewColumns: { key: string; header: string; align?: "left" | "right" | "center" }[];
  submit: (rows: ParsedRow[]) => Promise<{ count: number }>;
  successNote: string;
  /** Column -> its allowed values (compared case-insensitively - parseRow
   * already uppercases these columns before submitting). Catches a typo'd
   * or synonymous value (e.g. "refrigerated" instead of the app's own
   * "CHILLED") here, with the offending row number, instead of letting it
   * reach the backend as a 422 pattern-validation failure - which reports
   * back an array index into the submitted batch, not the original CSV row
   * number, so it's a much less useful error message for someone fixing a
   * pasted spreadsheet. */
  enumColumns?: Record<string, string[]>;
};

// Same enums the backend's Pydantic models enforce (app/models/schemas.py's
// AddProductRequest/AddLocationRequest) - kept here rather than imported so
// this page can validate a pasted CSV row locally, before it ever reaches
// the API.
const FRAGILITY_VALUES = ["LOW", "MEDIUM", "HIGH"];
const STORAGE_TYPE_VALUES = ["AMBIENT", "CHILLED", "FROZEN", "VAPE_DRAWER"];

const TYPE_CONFIG: Record<UploadType, TypeConfig> = {
  products: {
    label: "Products",
    template:
      "product_name,description,selling_price,unit_cost,category,length_cm,width_cm,height_cm,weight_kg,fragility,storage_type,stackable\n" +
      "Example Snack Box,,3.50,1.80,Snacks,20,15,8,0.4,LOW,AMBIENT,true\n",
    required: ["product_name", "selling_price", "unit_cost", "length_cm", "width_cm", "height_cm", "weight_kg"],
    help:
      "Required columns: product_name, selling_price, unit_cost, length_cm, width_cm, height_cm, weight_kg. Optional: " +
      "description, category, fragility (LOW/MEDIUM/HIGH), storage_type (AMBIENT/CHILLED/FROZEN/VAPE_DRAWER), stackable (true/false).",
    parseRow: (raw) => ({
      product_name: raw.product_name,
      description: raw.description || undefined,
      selling_price: Number(raw.selling_price),
      unit_cost: Number(raw.unit_cost),
      category: raw.category || undefined,
      length_cm: Number(raw.length_cm),
      width_cm: Number(raw.width_cm),
      height_cm: Number(raw.height_cm),
      weight_kg: Number(raw.weight_kg),
      fragility: (raw.fragility || "MEDIUM").toUpperCase(),
      storage_type: (raw.storage_type || "AMBIENT").toUpperCase(),
      stackable: raw.stackable ? raw.stackable.toLowerCase() !== "false" : true,
    }),
    enumColumns: { fragility: FRAGILITY_VALUES, storage_type: STORAGE_TYPE_VALUES },
    previewColumns: [
      { key: "product_name", header: "Product" },
      { key: "category", header: "Category" },
      { key: "selling_price", header: "Price", align: "right" },
      { key: "unit_cost", header: "Cost", align: "right" },
      { key: "weight_kg", header: "Weight (kg)", align: "right" },
      { key: "storage_type", header: "Storage" },
    ],
    submit: (rows) => adminApi.bulkAddProducts(rows),
    successNote: "they now appear under New Products Awaiting Placement on the Stock Optimizer page",
  },
  suppliers: {
    label: "Suppliers",
    template: "supplier_name,warehouse_id\n" + "Example Fresh Foods Ltd,\n" + "Lombard-Only Produce Co,1\n",
    required: ["supplier_name"],
    help:
      "Required column: supplier_name. Optional: warehouse_id (1, 2 or 3) to scope the supplier to one warehouse only " +
      "- leave blank for a supplier common to every warehouse.",
    parseRow: (raw) => ({
      supplier_name: raw.supplier_name,
      warehouse_id: raw.warehouse_id ? Number(raw.warehouse_id) : undefined,
    }),
    previewColumns: [
      { key: "supplier_name", header: "Supplier" },
      { key: "warehouse_id", header: "Warehouse", align: "center" },
    ],
    submit: (rows) => adminApi.bulkAddSuppliers(rows),
    successNote: "they now appear on the Suppliers admin page and are selectable across the dashboard",
  },
  locations: {
    label: "Storage Locations",
    template:
      "warehouse_id,location_code,storage_type,shelf_tier,sub_location_start,sub_location_count,is_overstock_tier,max_weight_kg,max_volume_cm3,note\n" +
      "1,12,AMBIENT,3,1,20,false,200,200000,\n",
    required: ["warehouse_id", "location_code", "storage_type", "max_weight_kg", "max_volume_cm3"],
    help:
      "Required columns: warehouse_id (1/2/3), location_code, storage_type (AMBIENT/CHILLED/FROZEN/VAPE_DRAWER), " +
      "max_weight_kg, max_volume_cm3 (per slot). Optional: shelf_tier, sub_location_start, sub_location_count " +
      "(defaults to a single slot), is_overstock_tier (true/false), note. Each row creates one location code's " +
      "range of sub-location slots - use one row per shelf tier.",
    parseRow: (raw) => ({
      warehouse_id: Number(raw.warehouse_id),
      location_code: Number(raw.location_code),
      storage_type: (raw.storage_type || "AMBIENT").toUpperCase(),
      shelf_tier: raw.shelf_tier ? Number(raw.shelf_tier) : 1,
      sub_location_start: raw.sub_location_start ? Number(raw.sub_location_start) : 1,
      sub_location_count: raw.sub_location_count ? Number(raw.sub_location_count) : 1,
      is_overstock_tier: raw.is_overstock_tier ? raw.is_overstock_tier.toLowerCase() === "true" : false,
      max_weight_kg: Number(raw.max_weight_kg),
      max_volume_cm3: Number(raw.max_volume_cm3),
      note: raw.note || undefined,
    }),
    enumColumns: { storage_type: STORAGE_TYPE_VALUES },
    previewColumns: [
      { key: "warehouse_id", header: "Warehouse", align: "center" },
      { key: "location_code", header: "Location" },
      { key: "storage_type", header: "Type" },
      { key: "shelf_tier", header: "Tier", align: "right" },
      { key: "sub_location_count", header: "Slots", align: "right" },
    ],
    submit: (rows) => adminApi.bulkAddLocations(rows),
    successNote: "they now appear on the Locations admin page and the Stock Optimizer's layout views",
  },
};

function parseCsv(text: string, config: TypeConfig): { rows: ParsedRow[]; errors: string[] } {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 0);
  if (lines.length < 2) return { rows: [], errors: ["Paste a header row plus at least one data row."] };

  const headers = lines[0].split(",").map((h) => h.trim());
  const missing = config.required.filter((r) => !headers.includes(r));
  if (missing.length > 0) return { rows: [], errors: [`Missing required column(s): ${missing.join(", ")}`] };

  // Columns that are text, not numbers - every other required column is
  // validated as numeric before being handed to the type's own parseRow.
  const textColumns = new Set(["supplier_name", "storage_type", "product_name", "note", "description", "category", "fragility"]);

  const errors: string[] = [];
  const rows: ParsedRow[] = [];
  lines.slice(1).forEach((line, i) => {
    const cells = line.split(",").map((c) => c.trim());
    const raw: Record<string, string> = {};
    headers.forEach((h, idx) => (raw[h] = cells[idx] ?? ""));

    const rowNum = i + 2;
    const missingRequired = config.required.filter((r) => !raw[r]);
    if (missingRequired.length > 0) {
      errors.push(`Row ${rowNum}: missing required value(s) for ${missingRequired.join(", ")}.`);
      return;
    }

    let rowValid = true;
    config.required.forEach((key) => {
      if (textColumns.has(key)) return;
      if (Number.isNaN(Number(raw[key]))) {
        errors.push(`Row ${rowNum}: "${key}" must be a number.`);
        rowValid = false;
      }
    });

    // Catch an invalid/misspelled enum value (e.g. "refrigerated" instead
    // of "CHILLED") here, with this CSV's own row number, rather than
    // letting it reach the backend as a 422 whose error location is an
    // index into the submitted batch, not a row someone can find in what
    // they pasted. Blank is fine here even for a column listed in
    // enumColumns - parseRow already defaults it (e.g. storage_type ->
    // "AMBIENT"), so an empty cell isn't a validation failure on its own.
    if (config.enumColumns) {
      Object.entries(config.enumColumns).forEach(([key, allowed]) => {
        const value = raw[key];
        if (!value) return;
        if (!allowed.includes(value.toUpperCase())) {
          errors.push(`Row ${rowNum}: "${key}" must be one of ${allowed.join("/")} (got "${value}").`);
          rowValid = false;
        }
      });
    }

    if (!rowValid) return;

    rows.push(config.parseRow(raw));
  });

  return { rows, errors };
}

export default function AdminBulkUploadPage() {
  const [uploadType, setUploadType] = useState<UploadType>("products");
  const [csvText, setCsvText] = useState("");
  const [parsed, setParsed] = useState<ParsedRow[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<{ count: number } | null>(null);

  const config = TYPE_CONFIG[uploadType];

  const switchType = (next: UploadType) => {
    setUploadType(next);
    setCsvText("");
    setParsed([]);
    setParseErrors([]);
    setResult(null);
    setSubmitError(null);
  };

  const handleFile = async (file: File) => {
    const text = await file.text();
    setCsvText(text);
    runParse(text);
  };

  const runParse = (text: string) => {
    setResult(null);
    setSubmitError(null);
    const { rows, errors } = parseCsv(text, config);
    setParsed(rows);
    setParseErrors(errors);
  };

  const submit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await config.submit(parsed);
      setResult({ count: res.count });
      setParsed([]);
      setCsvText("");
    } catch (e: any) {
      setSubmitError(e?.message || "Bulk upload failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // DataTable needs a unique keyField that exists on every row - product_name
  // works for the Products type but suppliers/locations don't have that
  // column, so every row gets a synthetic __row index for keying/sorting.
  const previewRows = parsed.map((r, i) => ({ ...r, __row: i }));

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Bulk Upload" />
        <div className="content-area">
          <div className="card admin-form-card" style={{ maxWidth: 720 }}>
            <div className="chart-card-header">
              <h3>Paste or Upload a CSV</h3>
            </div>
            <div className="form-field" style={{ maxWidth: 260, marginBottom: 4 }}>
              <label>What are you uploading?</label>
              <CustomDropdown
                value={uploadType}
                onChange={(v) => switchType(v as UploadType)}
                options={(Object.keys(TYPE_CONFIG) as UploadType[]).map((t) => ({ value: t, label: TYPE_CONFIG[t].label }))}
              />
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: -6, marginBottom: 10 }}>
              {config.help} This is a simple parser (plain comma-split, no quoted-comma support) - keep text fields
              free of commas.
            </p>
            <div className="form-grid">
              <div className="form-field">
                <label>Upload a .csv file</label>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
              </div>
              <div className="form-field">
                <label>...or paste CSV text</label>
                <textarea
                  rows={8}
                  value={csvText}
                  onChange={(e) => setCsvText(e.target.value)}
                  placeholder={config.template}
                  style={{ fontFamily: "monospace", fontSize: 12.5 }}
                />
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn-secondary btn-small" type="button" onClick={() => runParse(csvText)} disabled={!csvText.trim()}>
                  Preview
                </button>
                <button
                  className="btn-secondary btn-small"
                  type="button"
                  onClick={() => {
                    setCsvText(config.template);
                    runParse(config.template);
                  }}
                >
                  Load Example Template
                </button>
              </div>
            </div>

            {parseErrors.length > 0 && (
              <div className="empty-state" style={{ color: "var(--status-critical)" }}>
                {parseErrors.map((e, i) => (
                  <div key={i}>{e}</div>
                ))}
              </div>
            )}

            {parsed.length > 0 && (
              <>
                <div className="chart-card-header" style={{ marginTop: 16 }}>
                  <h3>
                    Preview ({parsed.length} {config.label.toLowerCase()})
                  </h3>
                </div>
                <DataTable
                  keyField="__row"
                  rows={previewRows}
                  pageSize={10}
                  columns={config.previewColumns}
                />
                <button className="btn-primary" onClick={submit} disabled={submitting} style={{ marginTop: 12 }}>
                  {submitting ? "Uploading..." : `Add All ${parsed.length} ${config.label}`}
                </button>
              </>
            )}

            {submitError && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{submitError}</p>}
            {result && (
              <p className="empty-state" style={{ color: "var(--status-good)" }}>
                Added {result.count} {config.label.toLowerCase()} - {config.successNote}.
              </p>
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
