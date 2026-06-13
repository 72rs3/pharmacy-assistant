import { createContext, useContext } from "react";

export const CustomerCartContext = createContext({
  items: [],
  addItem: () => {},
  removeItem: () => {},
  updateItemQuantity: () => {},
  clearCart: () => {},
  totalItems: 0,
  totalPrice: 0,
});

export const useCustomerCart = () => useContext(CustomerCartContext);
