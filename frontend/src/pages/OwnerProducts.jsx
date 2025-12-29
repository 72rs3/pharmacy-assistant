import { useEffect, useMemo, useState } from "react";
import { FileUp, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import api from "../api/axios";

const emptyDraft = {
  id: null,
  name: "",
  category: "",
  price: "",
  stock_level: "",
  image_url: "",
  description: "",
};

const normalizeText = (value) => String(value ?? "").trim();

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
  const hasHeader = headerCells.includes("name") || headerCells.includes("product") || headerCells.includes("product_name");

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
    setHeader("name", ["name", "product", "product_name"]);
    setHeader("category", ["category", "type"]);
    setHeader("price", ["price", "unit_price"]);
    setHeader("stock_level", ["stock_level", "stock", "quantity", "qty"]);
    setHeader("image_url", ["image_url", "image", "img"]);
    setHeader("description", ["description", "desc", "notes", "note"]);
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
    const category = normalizeText(getCell(cells, "category", 1)) || null;
    const priceRaw = normalizeText(getCell(cells, "price", 2));
    const stockRaw = normalizeText(getCell(cells, "stock_level", 3));
    const imageUrl = normalizeText(getCell(cells, "image_url", 4)) || null;
    const description = normalizeText(getCell(cells, "description", 5)) || null;

    if (!name) {
      errors.push({ row: rowNum, message: "Missing name" });
      continue;
    }

    const stockLevel = stockRaw ? Number.parseInt(stockRaw, 10) : null;
    if (stockRaw && (Number.isNaN(stockLevel) || stockLevel < 0)) {
      errors.push({ row: rowNum, message: "Stock must be a non-negative integer" });
      continue;
    }

    const price = priceRaw ? Number(priceRaw) : null;
    if (priceRaw && (Number.isNaN(price) || price < 0)) {
      errors.push({ row: rowNum, message: "Price must be a non-negative number" });
      continue;
    }

    items.push({
      name,
      category,
      price,
      stock_level: stockRaw ? stockLevel : null,
      image_url: imageUrl,
      description,
    });
  }

  return { items, errors };
};

export default function OwnerProducts() {
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState(emptyDraft);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isBulkOpen, setIsBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkFileName, setBulkFileName] = useState("");
  const [bulkUpdateFields, setBulkUpdateFields] = useState(false);
  const [bulkPreview, setBulkPreview] = useState(null);
  const [isBulkImporting, setIsBulkImporting] = useState(false);
  const [bulkStatus, setBulkStatus] = useState("");

  const loadProducts = async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await api.get("/products/owner");
      setProducts(res.data ?? []);
    } catch (e) {
      setProducts([]);
      setError(e?.response?.data?.detail ?? "Failed to load products");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProducts();
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return products;
    return products.filter((product) => {
      const haystack = `${product.name ?? ""} ${product.category ?? ""}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [products, search]);

  const openNew = () => {
    setDraft(emptyDraft);
    setIsModalOpen(true);
  };

  const openEdit = (product) => {
    setDraft({
      id: product.id,
      name: product.name ?? "",
      category: product.category ?? "",
      price: String(product.price ?? ""),
      stock_level: String(product.stock_level ?? ""),
      image_url: product.image_url ?? "",
      description: product.description ?? "",
    });
    setIsModalOpen(true);
  };

  const saveProduct = async (event) => {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    setError("");

    const payload = {
      name: draft.name.trim(),
      category: draft.category.trim() || null,
      price: Number(draft.price),
      stock_level: Number(draft.stock_level),
      image_url: draft.image_url.trim() || null,
      description: draft.description.trim() || null,
    };

    try {
      if (draft.id) {
        await api.put(`/products/owner/${draft.id}`, payload);
      } else {
        await api.post("/products/owner", payload);
      }
      setIsModalOpen(false);
      setDraft(emptyDraft);
      await loadProducts();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to save product");
    } finally {
      setIsSaving(false);
    }
  };

  const deleteProduct = async (product) => {
    const ok = window.confirm(`Delete "${product.name}"? This cannot be undone.`);
    if (!ok) return;
    setError("");
    try {
      await api.delete(`/products/owner/${product.id}`);
      await loadProducts();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to delete product");
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
      const res = await api.post("/products/owner/bulk-import", {
        items: parsed.items,
        update_fields: Boolean(bulkUpdateFields),
      });
      const out = res.data;
      const errorCount = Array.isArray(out?.errors) ? out.errors.length : 0;
      setBulkStatus(`Imported. Created ${out?.created ?? 0}, updated ${out?.updated ?? 0}${errorCount ? ` (${errorCount} errors)` : ""}.`);
      await loadProducts();
    } catch (e) {
      setError(e?.response?.data?.detail ?? "Failed to bulk import products");
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

  return (
    <div className="max-w-6xl mx-auto">
      <div className="bg-white rounded-2xl shadow-[0_24px_60px_rgba(15,23,42,0.12)] border border-slate-200 overflow-hidden">
        <div className="px-6 py-5 flex items-center justify-between gap-4 border-b border-slate-200">
          <div className="min-w-0">
            <h1 className="text-3xl font-semibold text-slate-900 tracking-tight">Shop Products</h1>
            <p className="text-sm text-slate-500 mt-1">Manage non-medicine products shown in the customer shop.</p>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={loadProducts}
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
              Add Product
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
          {bulkStatus ? (
            <div className="rounded-xl border border-blue-200 bg-blue-50 text-blue-900 px-4 py-3 text-sm">{bulkStatus}</div>
          ) : null}

          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="productSearch">
                Search
              </label>
              <input
                id="productSearch"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white focus:outline-none focus:ring-4 focus:ring-blue-100"
                placeholder="Search by name, category..."
              />
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="overflow-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="text-left font-semibold px-5 py-4">Name</th>
                    <th className="text-left font-semibold px-5 py-4">Category</th>
                    <th className="text-left font-semibold px-5 py-4">Price</th>
                    <th className="text-left font-semibold px-5 py-4">Stock</th>
                    <th className="text-right font-semibold px-5 py-4">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-6 text-slate-500">
                        Loading products...
                      </td>
                    </tr>
                  ) : filtered.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-6 text-slate-500">
                        No products found.
                      </td>
                    </tr>
                  ) : (
                    filtered.map((product) => (
                      <tr key={product.id} className="border-t border-slate-100 hover:bg-slate-50/70">
                        <td className="px-5 py-4">
                          <div className="font-medium text-slate-900">{product.name}</div>
                        </td>
                        <td className="px-5 py-4 text-slate-700">{product.category ?? "-"}</td>
                        <td className="px-5 py-4 text-slate-700">${Number(product.price ?? 0).toFixed(2)}</td>
                        <td className="px-5 py-4 text-slate-700">{Number(product.stock_level ?? 0)}</td>
                        <td className="px-5 py-4">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => openEdit(product)}
                              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
                            >
                              <Pencil className="w-4 h-4" />
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => deleteProduct(product)}
                              className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-red-200 text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 py-10">
          <div className="w-full max-w-2xl bg-white rounded-2xl shadow-[0_24px_80px_rgba(2,6,23,0.45)] border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">{draft.id ? "Edit product" : "Add product"}</h2>
                <p className="text-sm text-slate-500">This will appear in the customer shop.</p>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={saveProduct} className="p-6 space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodName">
                    Name *
                  </label>
                  <input
                    id="prodName"
                    value={draft.name}
                    onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    placeholder="e.g., Toothpaste"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodCategory">
                    Category
                  </label>
                  <input
                    id="prodCategory"
                    value={draft.category}
                    onChange={(e) => setDraft((prev) => ({ ...prev, category: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    placeholder="e.g., Oral Care"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodPrice">
                    Price *
                  </label>
                  <input
                    id="prodPrice"
                    value={draft.price}
                    onChange={(e) => setDraft((prev) => ({ ...prev, price: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    type="number"
                    step="0.01"
                    min="0"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodStock">
                    Stock *
                  </label>
                  <input
                    id="prodStock"
                    value={draft.stock_level}
                    onChange={(e) => setDraft((prev) => ({ ...prev, stock_level: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    type="number"
                    min="0"
                    required
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodImage">
                    Image URL (optional)
                  </label>
                  <input
                    id="prodImage"
                    value={draft.image_url}
                    onChange={(e) => setDraft((prev) => ({ ...prev, image_url: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    placeholder="https://..."
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-600 mb-1" htmlFor="prodDesc">
                    Description (optional)
                  </label>
                  <textarea
                    id="prodDesc"
                    value={draft.description}
                    onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
                    className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-4 focus:ring-blue-100"
                    rows={3}
                  />
                </div>
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
                <h2 className="text-lg font-semibold text-slate-900">Bulk Import Products</h2>
                <p className="text-sm text-slate-500">Upload CSV/XLSX or paste rows (tab-separated works best).</p>
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
                    placeholder={`name\tcategory\tprice\tstock_level\timage_url\tdescription\nToothpaste\tOral Care\t4.99\t50\thttps://...\tFluoride toothpaste\nBaby wipes\tBaby Care\t6.99\t100\t\taction: sensitive`}
                  />

                  <label className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 text-slate-700">
                    <span className="text-sm">Update details for existing products (price/category/image/description)</span>
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
                            <th className="text-left font-semibold px-3 py-2">Category</th>
                            <th className="text-left font-semibold px-3 py-2">Stock</th>
                            <th className="text-left font-semibold px-3 py-2">Price</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(bulkPreview?.items ?? []).slice(0, 25).map((row, idx) => (
                            <tr key={`${row.name}-${idx}`} className="border-t border-slate-100">
                              <td className="px-3 py-2">{row.name}</td>
                              <td className="px-3 py-2">{row.category || "—"}</td>
                              <td className="px-3 py-2">{row.stock_level ?? "—"}</td>
                              <td className="px-3 py-2">{row.price ?? "—"}</td>
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
                      Tip: include a header row to import columns in any order (name, category, price, stock_level, image_url, description).
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
