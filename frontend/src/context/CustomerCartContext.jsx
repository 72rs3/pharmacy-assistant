import { createContext, useContext, useEffect, useMemo, useState } from "react";

const CART_STORAGE_KEY = "customer_cart_items";

const CustomerCartContext = createContext({
  items: [],
  addItem: () => {},
  removeItem: () => {},
  updateItemQuantity: () => {},
  clearCart: () => {},
  totalItems: 0,
  totalPrice: 0,
});

const readStoredItems = () => {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(CART_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export function CustomerCartProvider({ children }) {
  const [items, setItems] = useState(() => readStoredItems());

  useEffect(() => {
    if (typeof window === "undefined") return;
    localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(items));
  }, [items]);

  const addItem = (item) => {
    if (!item) return;
    const id = String(item.id ?? "");
    if (!id) return;
    setItems((prev) => {
      const existing = prev.find((entry) => String(entry.id) === id);
      if (!existing) {
        return [
          ...prev,
          {
            id,
            name: String(item.name ?? "Item"),
            price: Number(item.price ?? 0),
            image: item.image ?? "",
            quantity: 1,
          },
        ];
      }
      return prev.map((entry) =>
        String(entry.id) === id ? { ...entry, quantity: entry.quantity + 1 } : entry
      );
    });
  };

  const removeItem = (id) => {
    setItems((prev) => prev.filter((entry) => String(entry.id) !== String(id)));
  };

  const updateItemQuantity = (id, nextQuantity) => {
    setItems((prev) => {
      const quantity = Number(nextQuantity);
      if (!Number.isFinite(quantity) || quantity <= 0) {
        return prev.filter((entry) => String(entry.id) !== String(id));
      }
      return prev.map((entry) =>
        String(entry.id) === String(id) ? { ...entry, quantity } : entry
      );
    });
  };

  const clearCart = () => setItems([]);

  const totalItems = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.quantity ?? 0), 0),
    [items]
  );

  const totalPrice = useMemo(
    () =>
      items.reduce(
        (sum, item) => sum + Number(item.quantity ?? 0) * Number(item.price ?? 0),
        0
      ),
    [items]
  );

  const value = useMemo(
    () => ({
      items,
      addItem,
      removeItem,
      updateItemQuantity,
      clearCart,
      totalItems,
      totalPrice,
    }),
    [items, totalItems, totalPrice]
  );

  return <CustomerCartContext.Provider value={value}>{children}</CustomerCartContext.Provider>;
}

export const useCustomerCart = () => useContext(CustomerCartContext);
