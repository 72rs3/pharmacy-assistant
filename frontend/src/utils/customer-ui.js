import { createContext, useContext } from "react";

export const CustomerUiContext = createContext({
  openChat: () => {},
});

export const useCustomerUi = () => useContext(CustomerUiContext);
