import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, FileUp, Plus, RefreshCw, Sparkles, Trash2, Pencil } from "lucide-react";
import api from "../api/axios";

const LOW_STOCK_THRESHOLD = 10;

const emptyDraft = {
  id: null,
  name: "",
  dosage: "",
  category: "",
  price: "",
  stock_level: "",
  expiry_date: "",
  prescription_required: false,
  side_effects: "",
};

const formatDate = (value) => {
  if (!value) return "?";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toISOString().slice(0, 10);
};

const isExpiringSoon = (value, days = 30) => {
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  const threshold = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
  return date <= threshold;
};

const normalizeText = (value) => String(value ?? "").trim();

const medicineKey = (name, dosage) => {
  const normalizedName = normalizeText(name).toLowerCase();
  const normalizedDosage = normalizeText(dosage).toLowerCase();
  return `${normalizedName}||${normalizedDosage}`;
};

const splitDelimited = (line, delimiter) => {
  if (delimiter === "\t") return String(line ?? "").split("\t");
  const input = String(line ?? "");
  const out = [];
  let buf = "";
  let inQuotes = false;
  for (let i = 0; i < input.length; i += 1) {
    const ch = input[i];
    if (ch === '"') {
      if (inQuotes && input[i + 1] === '"') {
        buf += '"';
        i += 1;
        continue;
      }
      inQuotes = !inQuotes;
      continue;
    }
    if (!inQuotes && ch === delimiter) {
      out.push(buf);
      buf = "";
      continue;
    }
    buf += ch;
  }
  out.push(buf);
  return out;
};

const parseBool = (raw) => {
  const v = normalizeText(raw).toLowerCase();
  if (!v) return null;
  if (["1", "true", "yes", "y", "rx", "prescription"].includes(v)) return true;
  if (["0", "false", "no", "n", "otc"].includes(v)) return false;
  return null;
};

const parseBulkText = (text) => {
  const lines = String(text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n")
    .map((l) => l.trimEnd())
    .filter((l) => l.trim().length > 0);

  if (lines.length === 0) return { items: [], errors: [] };

  const delimiter = lines.some((l) => l.includes("\t")) ? "\t" : ",";
  const headerCells = splitDelimited(lines[0], delimiter).map((c) => normalizeText(c).toLowerCase());
  const hasHeader = headerCells.includes("name") || headerCells.includes("medicine") || headerCells.includes("medicine_name");

  const headerIndex = new Map();
  const setHeader = (key, aliases) => {
    for (const alias of aliases) {
      const idx = headerCells.indexOf(alias);
      if (idx >= 0) {
        headerIndex.set(key, idx);
        return;
      }
    }
  };

  if (hasHeader) {
    setHeader("name", ["name", "medicine", "medicine_name"]);
    setHeader("dosage", ["dosage", "strength"]);
    setHeader("category", ["category", "type"]);
    setHeader("price", ["price", "unit_price"]);
    setHeader("stock_delta", ["quantity", "qty", "stock", "stock_level", "stock_delta"]);
    setHeader("expiry_date", ["expiry_date", "expiry", "exp"]);
    setHeader("prescription_required", ["prescription_required", "rx", "prescription"]);
    setHeader("side_effects", ["side_effects", "notes", "note"]);
  }

  const errors = [];
  const items = [];
  const startIndex = hasHeader ? 1 : 0;

  const getCell = (cells, key, fallbackIndex) => {
    const idx = hasHeader ? headerIndex.get(key) : fallbackIndex;
    if (idx === undefined || idx === null) return "";
    return cells[idx] ?? "";
  };

  for (let i = startIndex; i < lines.length; i += 1) {
    const cells = splitDelimited(lines[i], delimiter);
    const rowNum = i + 1;

    const name = normalizeText(getCell(cells, "name", 0));
    const dosage = normalizeText(getCell(cells, "dosage", 1)) || null;
    const category = normalizeText(getCell(cells, "category", 2)) || null;
    const priceRaw = normalizeText(getCell(cells, "price", 3));
    const qtyRaw = normalizeText(getCell(cells, "stock_delta", 4));
    const expiry = normalizeText(getCell(cells, "expiry_date", 5)) || null;
    const rxRaw = normalizeText(getCell(cells, "prescription_required", 6));
    const notes = normalizeText(getCell(cells, "side_effects", 7)) || null;

    if (!name) {
      errors.push({ row: rowNum, message: "Missing name" });
      continue;
    }

    const stockDelta = qtyRaw ? Number.parseInt(qtyRaw, 10) : 0;
    if (Number.isNaN(stockDelta) || stockDelta < 0) {
      errors.push({ row: rowNum, message: "Quantity must be a non-negative integer" });
      continue;
    }

    const price = priceRaw ? Number(priceRaw) : null;
    if (priceRaw && (Number.isNaN(price) || price < 0)) {
      errors.push({ row: rowNum, message: "Price must be a non-negative number" });
      continue;
    }

    const rx = parseBool(rxRaw);
    if (rxRaw && rx === null) {
      errors.push({ row: rowNum, message: "Prescription flag must be one of: yes/no, true/false, 1/0, rx/otc" });
      continue;
    }

    if (expiry && !/^\d{4}-\d{2}-\d{2}$/.test(expiry)) {
      errors.push({ row: rowNum, message: "Expiry date must be YYYY-MM-DD" });
      continue;
    }

    items.push({
      name,
      dosage,
      category,
      price,
      stock_delta: stockDelta,
      expiry_date: expiry,
      prescription_required: rx,
      side_effects: notes,
    });
  }

  return { items, errors };
};

export default function OwnerInventory() {
  const [medicines, setMedicines] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState(emptyDraft);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexStatus, setReindexStatus] = useState("");
  const [quick, setQuick] = useState({ name: "", dosage: "", quantity: "", expiry_date: "" });
  const [isQuickSaving, setIsQuickSaving] = useState(false);
  const [isBulkOpen, setIsBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkUpdateFields, setBulkUpdateFields] = useState(false);
  const [bulkPreview, setBulkPreview] = useState(null);
  const [isBulkImporting, setIsBulkImporting] = useState(false);
  const [bulkStatus, setBulkStatus] = useState("");
  const [bulkFileName, setBulkFileName] = useState("");

  const loadMedicines = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/medicines/owner");
      setMedicines(res.data ?? []);
    } catch (e) {
      setMedicines([]);
      setError(e?.response?.data?.detail ?? "Failed to load inventory");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMedicines();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return medicines;
    return medicines.filter((medicine) => {
      const haystack = `${medicine.name ?? ""} ${medicine.dosage ?? ""} ${medicine.category ?? ""}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [medicines, search]);

  const medicinesByKey = useMemo(() => {
    const map = new Map();
    const byName = new Map();
    for (const medicine of medicines) {
      const key = medicineKey(medicine.name, medicine.dosage);
      map.set(key, medicine);
      const nameKey = medicineKey(medicine.name, "");
      if (!byName.has(nameKey)) byName.set(nameKey, []);
      byName.get(nameKey).push(medicine);
    }
    return { map, byName };
  }, [medicines]);

  const quickMatch = useMemo(() => {
    const name = normalizeText(quick.name);
    if (!name) return null;
    const dosage = normalizeText(quick.dosage);
    const direct = medicinesByKey.map.get(medicineKey(name, dosage));
    if (direct) return direct;
    if (!dosage) {
      const candidates = medicinesByKey.byName.get(medicineKey(name, "")) ?? [];
      if (candidates.length === 1) return candidates[0];
    }
    return null;
  }, [quick.name, quick.dosage, medicinesByKey]);

  const openNew = () => {
    setDraft(emptyDraft);
    setIsModalOpen(true);
  };

  const openEdit = (medicine) => {
    setDraft({
      id: medicine.id,
      name: medicine.name ?? "",
      dosage: medicine.dosage ?? "",
      category: medicine.category ?? "",
      price: String(medicine.price ?? ""),
      stock_level: String(medicine.stock_level ?? ""),
      expiry_date: medicine.expiry_date ? String(medicine.expiry_date).slice(0, 10) : "",
      prescription_required: Boolean(medicine.prescription_required),
      side_effects: medicine.side_effects ?? "",
    });
    setIsModalOpen(true);
  };

  const saveMedicine = async (event) => {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    setError("");

    const payload = {
      name: draft.name.trim(),
      category: draft.category.trim() || null,
      price: Number(draft.price),
      stock_level: Number(draft.stock_level),
      expiry_date: draft.expiry_date ? draft.expiry_date : null,
      prescription_required: Boolean(draft.prescription_required),
      dosage: draft.dosage.trim() || null,
      side_effects: draft.side_effects.trim() || null,
    };

    try {
      if (draft.id) {
        await api.put(`/medicines/owner/${draft.id}`, payload);
      } else {
        await api.post("/medicines/owner", payload);
      }
      setIsModalOpen(false);
      setDraft(emptyDraft);
      await loadMedicines();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to save medicine");
    } finally {
      setIsSaving(false);
    }
  };

  const deleteMedicine = async (medicine) => {
    const ok = window.confirm(`Delete "${medicine.name}"? This cannot be undone.`);
    if (!ok) return;
    setError("");
    try {
      await api.delete(`/medicines/owner/${medicine.id}`);
      await loadMedicines();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to delete medicine");
    }
  };

  const submitQuick = async (event) => {
    event.preventDefault();
    if (isQuickSaving) return;
    setError("");
    setBulkStatus("");

    const name = normalizeText(quick.name);
    const dosage = normalizeText(quick.dosage);
    const qty = Number.parseInt(normalizeText(quick.quantity), 10);
    if (!name) {
      setError("Quick add: name is required");
      return;
    }
    if (Number.isNaN(qty) || qty <= 0) {
      setError("Quick add: quantity must be a positive integer");
      return;
    }

    setIsQuickSaving(true);
    try {
      if (quickMatch?.id) {
        await api.post(`/medicines/owner/${quickMatch.id}/stock-in`, {
          quantity_delta: qty,
          expiry_date: quick.expiry_date ? quick.expiry_date : null,
        });
        setQuick({ name: "", dosage: "", quantity: "", expiry_date: "" });
        await loadMedicines();
        return;
      }

      setDraft({
        ...emptyDraft,
        name,
        dosage,
        stock_level: String(qty),
        expiry_date: quick.expiry_date ? quick.expiry_date : "",
      });
      setIsModalOpen(true);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to add stock");
    } finally {
      setIsQuickSaving(false);
    }
  };

  const previewBulk = () => {
    setError("");
    setBulkStatus("");
    setBulkPreview(parseBulkText(bulkText));
  };

  const importBulk = async () => {
    if (isBulkImporting) return;
    setError("");
    setBulkStatus("");
    const parsed = bulkPreview ?? parseBulkText(bulkText);
    setBulkPreview(parsed);
    if ((parsed.errors ?? []).length > 0) {
      setError("Fix bulk import errors before importing.");
      return;
    }
    if ((parsed.items ?? []).length === 0) {
      setError("Bulk import has no rows.");
      return;
    }

    setIsBulkImporting(true);
    try {
      const res = await api.post("/medicines/owner/bulk-import", {
        items: parsed.items,
        update_fields: Boolean(bulkUpdateFields),
      });
      const out = res.data;
      const errorCount = Array.isArray(out?.errors) ? out.errors.length : 0;
      setBulkStatus(
        `Imported. Created ${out?.created ?? 0}, updated ${out?.updated ?? 0}, stock-in ${out?.stock_in ?? 0}${
          errorCount ? ` (${errorCount} errors)` : ""
        }.`
      );
      await loadMedicines();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to bulk import medicines");
    } finally {
      setIsBulkImporting(false);
    }
  };

  const loadBulkFile = async (file) => {
    if (!file) return;
    setError("");
    setBulkStatus("");
    setBulkPreview(null);

    const name = String(file.name ?? "").trim();
    setBulkFileName(name);

    const ext = name.toLowerCase().split(".").pop();
    try {
      if (ext === "xlsx" || ext === "xls") {
        const [{ read, utils }] = await Promise.all([import("xlsx")]);
        const data = await file.arrayBuffer();
        const workbook = read(data, { type: "array" });
        const firstSheetName = workbook.SheetNames?.[0];
        if (!firstSheetName) {
          setError("Excel file has no sheets.");
          return;
        }
        const sheet = workbook.Sheets[firstSheetName];
        const rows = utils.sheet_to_json(sheet, { header: 1, defval: "" });
        if (!Array.isArray(rows) || rows.length === 0) {
          setError("Excel sheet is empty.");
          return;
        }
        const tsv = rows
          .map((row) =>
            (Array.isArray(row) ? row : [row]).map((cell) => String(cell ?? "").replaceAll("\t", " ").trimEnd()).join("\t")
          )
          .join("\n");
        setBulkText(tsv);
        setBulkPreview(parseBulkText(tsv));
        return;
      }

      const text = await file.text();
      setBulkText(text);
      setBulkPreview(parseBulkText(text));
    } catch (e) {
      setError(e?.message ?? "Failed to read import file");
    }
  };

  const reindexAi = async () => {
    setError("");
    setReindexStatus("");
    setIsReindexing(true);
    try {
      const res = await api.post("/ai/rag/reindex");
      setReindexStatus(`AI index updated (${res.data?.chunks ?? 0} chunks).`);
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to reindex AI");
    } finally {
      setIsReindexing(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Inventory Management</h1>
            <p className="text-sm text-slate-500 mt-1">Manage stock, expiry dates, and prescription flags.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={reindexAi}
              disabled={isReindexing}
              className="hidden sm:inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              title="Reindex AI"
            >
              <Sparkles className="w-4 h-4" />
              {isReindexing ? "Reindexing..." : "Reindex"}
            </button>
            <button
              type="button"
              onClick={loadMedicines}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-60"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
            <button
              type="button"
              onClick={openNew}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
            >
              <Plus className="w-4 h-4" />
              Add New Item
            </button>
            <button
              type="button"
              onClick={() => {
                setIsBulkOpen(true);
                setBulkStatus("");
                setBulkPreview(null);
                setBulkFileName("");
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 shadow-sm"
            >
              <FileUp className="w-4 h-4" />
              Bulk Import
            </button>
          </div>
        </div>

        <div className="p-6 bg-slate-50/60 space-y-4">
          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-sm">{error}</div>
            ) : null}
          {reindexStatus ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 px-4 py-3 text-sm">
              {reindexStatus}
            </div>
          ) : null}
          {bulkStatus ? (
            <div className="rounded-xl border border-blue-200 bg-blue-50 text-blue-900 px-4 py-3 text-sm">
              {bulkStatus}
            </div>
          ) : null}

          <form onSubmit={submitQuick} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4">
            <div className="flex flex-col lg:flex-row lg:items-end gap-3">
              <div className="flex-1">
                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="quickName">
                  Quick add (name)
                </label>
                <input
                  id="quickName"
                  value={quick.name}
                  onChange={(e) => setQuick((prev) => ({ ...prev, name: e.target.value }))}
                  list="medicineNameHints"
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                  placeholder="e.g., Paracetamol"
                />
                <datalist id="medicineNameHints">
                  {medicines.slice(0, 200).map((m) => (
                    <option key={m.id} value={m.name ?? ""} />
                  ))}
                </datalist>
              </div>
              <div className="w-full lg:w-48">
                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="quickDosage">
                  Dosage (optional)
                </label>
                <input
                  id="quickDosage"
                  value={quick.dosage}
                  onChange={(e) => setQuick((prev) => ({ ...prev, dosage: e.target.value }))}
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                  placeholder="e.g., 500mg"
                />
              </div>
              <div className="w-full lg:w-40">
                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="quickQty">
                  Quantity *
                </label>
                <input
                  id="quickQty"
                  value={quick.quantity}
                  onChange={(e) => setQuick((prev) => ({ ...prev, quantity: e.target.value }))}
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                  type="number"
                  min="1"
                  required
                />
              </div>
              <div className="w-full lg:w-44">
                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="quickExpiry">
                  Expiry date
                </label>
                <input
                  id="quickExpiry"
                  value={quick.expiry_date}
                  onChange={(e) => setQuick((prev) => ({ ...prev, expiry_date: e.target.value }))}
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                  type="date"
                />
              </div>
              <button
                type="submit"
                disabled={isQuickSaving}
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-60"
              >
                {quickMatch ? `Add stock to "${quickMatch.name}"` : "Create item"}
              </button>
            </div>
            <div className="text-xs text-slate-500 mt-2">
              {quickMatch ? "Matched existing medicine (stock will be increased)." : "No exact match (opens the create form)."}
            </div>
          </form>

          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="inventorySearch">
                Search
              </label>
              <input
                id="inventorySearch"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                placeholder="Search by name, dosage, category..."
              />
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                  <tr>
                    <th className="text-left font-semibold px-5 py-4">Name</th>
                    <th className="text-left font-semibold px-5 py-4">Quantity</th>
                    <th className="text-left font-semibold px-5 py-4">Expiry Date</th>
                    <th className="text-right font-semibold px-5 py-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {isLoading ? (
                    <tr>
                      <td colSpan={4} className="px-5 py-6 text-slate-500">
                        Loading inventory...
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-5 py-6 text-slate-500">
                        No items found.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((medicine) => {
                      const stock = Number(medicine.stock_level ?? 0);
                      const lowStock = stock > 0 && stock <= LOW_STOCK_THRESHOLD;
                      const outOfStock = stock <= 0;
                      const showExpiryWarning = isExpiringSoon(medicine.expiry_date);
                      return (
                        <tr key={medicine.id} className="hover:bg-slate-50/70">
                          <td className="px-5 py-4">
                            <div className="font-semibold text-slate-900">{medicine.name}</div>
                            <div className="text-xs text-slate-500 mt-1">
                              {medicine.dosage ? medicine.dosage : null}
                              {medicine.dosage && medicine.prescription_required ? " ? " : null}
                              {medicine.prescription_required ? "Prescription" : null}
                              {!medicine.dosage && !medicine.prescription_required ? "?" : null}
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            <div className="inline-flex items-center gap-2">
                              <span
                                className={`w-2.5 h-2.5 rounded-full ${
                                  outOfStock ? "bg-red-500" : lowStock ? "bg-amber-500" : "bg-emerald-500"
                                }`}
                                aria-hidden="true"
                              />
                              <span className="text-slate-900">{stock}</span>
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            <div className="inline-flex items-center gap-2 text-slate-900">
                              <span>{formatDate(medicine.expiry_date)}</span>
                              {showExpiryWarning ? (
                                <span title="Expiring soon">
                                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                                </span>
                              ) : null}
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => openEdit(medicine)}
                                className="p-2 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50"
                                aria-label={`Edit ${medicine.name}`}
                              >
                                <Pencil className="w-4 h-4" />
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteMedicine(medicine)}
                                className="p-2 rounded-lg border border-slate-200 text-slate-700 hover:bg-red-50 hover:border-red-200 hover:text-red-700"
                                aria-label={`Delete ${medicine.name}`}
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/30"
            onClick={() => setIsModalOpen(false)}
            aria-label="Close modal"
          />
          <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div className="text-lg font-semibold text-slate-900">{draft.id ? "Edit item" : "Add new item"}</div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50"
              >
                Close
              </button>
            </div>
            <form onSubmit={saveMedicine} className="p-6 grid gap-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medName">
                    Name *
                  </label>
                  <input
                    id="medName"
                    value={draft.name}
                    onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medDosage">
                    Dosage
                  </label>
                  <input
                    id="medDosage"
                    value={draft.dosage}
                    onChange={(e) => setDraft((prev) => ({ ...prev, dosage: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    placeholder="e.g., 500mg"
                  />
                </div>
              </div>

              <div className="grid sm:grid-cols-3 gap-4">
                <div className="sm:col-span-1">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medQty">
                    Quantity *
                  </label>
                  <input
                    id="medQty"
                    value={draft.stock_level}
                    onChange={(e) => setDraft((prev) => ({ ...prev, stock_level: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    type="number"
                    min="0"
                    required
                  />
                </div>
                <div className="sm:col-span-1">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medExpiry">
                    Expiry date
                  </label>
                  <input
                    id="medExpiry"
                    value={draft.expiry_date}
                    onChange={(e) => setDraft((prev) => ({ ...prev, expiry_date: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    type="date"
                  />
                </div>
                <div className="sm:col-span-1">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medPrice">
                    Price *
                  </label>
                  <input
                    id="medPrice"
                    value={draft.price}
                    onChange={(e) => setDraft((prev) => ({ ...prev, price: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    type="number"
                    step="0.01"
                    min="0"
                    required
                  />
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medCategory">
                    Category
                  </label>
                  <input
                    id="medCategory"
                    value={draft.category}
                    onChange={(e) => setDraft((prev) => ({ ...prev, category: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    placeholder="e.g., Antibiotic"
                  />
                </div>
                <label className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-700">
                  <span className="text-sm">Prescription required</span>
                  <input
                    type="checkbox"
                    checked={draft.prescription_required}
                    onChange={(e) => setDraft((prev) => ({ ...prev, prescription_required: e.target.checked }))}
                    className="accent-blue-600"
                  />
                </label>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="medSideEffects">
                  Side effects / notes
                </label>
                <textarea
                  id="medSideEffects"
                  value={draft.side_effects}
                  onChange={(e) => setDraft((prev) => ({ ...prev, side_effects: e.target.value }))}
                  className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  rows={3}
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-5 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                >
                  {isSaving ? "Saving..." : "Save"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {isBulkOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-10">
          <div className="w-full max-w-4xl bg-white rounded-2xl shadow-[0_24px_80px_rgba(2,6,23,0.45)] border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Bulk Import Medicines</h2>
                <p className="text-sm text-slate-500">Upload a CSV/XLSX or paste rows (tab-separated works best).</p>
              </div>
              <button
                type="button"
                onClick={() => setIsBulkOpen(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="grid lg:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <label className="block text-xs font-medium text-slate-600" htmlFor="bulkFile">
                      Upload file (CSV/XLSX)
                    </label>
                    <div className="text-xs text-slate-500">{bulkFileName ? `Selected: ${bulkFileName}` : ""}</div>
                  </div>
                  <input
                    id="bulkFile"
                    type="file"
                    accept=".csv,.tsv,.txt,.xlsx,.xls"
                    onChange={(e) => loadBulkFile(e.target.files?.[0] ?? null)}
                    className="block w-full text-sm text-slate-700 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border file:border-slate-200 file:bg-white file:text-slate-700 hover:file:bg-slate-50"
                  />
                  <label className="block text-xs font-medium text-slate-600" htmlFor="bulkText">
                    Paste data (optional)
                  </label>
                  <textarea
                    id="bulkText"
                    value={bulkText}
                    onChange={(e) => setBulkText(e.target.value)}
                    className="w-full min-h-[220px] px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100 font-mono text-xs"
                    placeholder={`name\tdosage\tcategory\tprice\tquantity\texpiry_date\trx\tnotes\nParacetamol\t500mg\tPain relief\t12.5\t100\t2026-05-01\totc\t-\nAmoxicillin\t250mg\tAntibiotic\t45\t30\t2025-11-20\trx\tDrowsiness`}
                  />
                  <label className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-700">
                    <span className="text-sm">Update details for existing items (price/category/rx/notes)</span>
                    <input
                      type="checkbox"
                      checked={bulkUpdateFields}
                      onChange={(e) => setBulkUpdateFields(e.target.checked)}
                      className="accent-blue-600"
                    />
                  </label>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={previewBulk}
                      className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                    >
                      Preview
                    </button>
                    <button
                      type="button"
                      onClick={importBulk}
                      disabled={isBulkImporting}
                      className="px-5 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      {isBulkImporting ? "Importing..." : "Import"}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-900">Preview</h3>
                    <div className="text-xs text-slate-500">
                      {(bulkPreview?.items?.length ?? 0)} rows, {(bulkPreview?.errors?.length ?? 0)} errors
                    </div>
                  </div>
                  <div className="rounded-2xl border border-slate-200 overflow-hidden">
                    <div className="max-h-[320px] overflow-auto bg-white">
                      <table className="min-w-full text-xs">
                        <thead className="bg-slate-50 sticky top-0">
                          <tr>
                            <th className="text-left font-semibold px-3 py-2">Name</th>
                            <th className="text-left font-semibold px-3 py-2">Dosage</th>
                            <th className="text-left font-semibold px-3 py-2">Qty</th>
                            <th className="text-left font-semibold px-3 py-2">Price</th>
                            <th className="text-left font-semibold px-3 py-2">Expiry</th>
                            <th className="text-left font-semibold px-3 py-2">Rx</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(bulkPreview?.items ?? []).slice(0, 25).map((row, idx) => (
                            <tr key={`${row.name}-${idx}`} className="border-t border-slate-100">
                              <td className="px-3 py-2">{row.name}</td>
                              <td className="px-3 py-2">{row.dosage || "—"}</td>
                              <td className="px-3 py-2">{row.stock_delta}</td>
                              <td className="px-3 py-2">{row.price ?? "—"}</td>
                              <td className="px-3 py-2">{row.expiry_date || "—"}</td>
                              <td className="px-3 py-2">{row.prescription_required === null ? "—" : row.prescription_required ? "Yes" : "No"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {(bulkPreview?.errors ?? []).length ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 text-red-800 px-4 py-3 text-xs space-y-1">
                      {bulkPreview.errors.slice(0, 8).map((err) => (
                        <div key={`${err.row}-${err.message}`}>
                          Row {err.row}: {err.message}
                        </div>
                      ))}
                      {bulkPreview.errors.length > 8 ? <div>…and {bulkPreview.errors.length - 8} more</div> : null}
                    </div>
                  ) : (
                    <div className="text-xs text-slate-500">
                      Tip: include a header row to import columns in any order (name, dosage, category, price, quantity, expiry_date, rx, notes).
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
