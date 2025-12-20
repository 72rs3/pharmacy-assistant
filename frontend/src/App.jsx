import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AdminRoute from "./components/AdminRoute";
import AdminPharmacies from "./pages/AdminPharmacies";
import OwnerRoute from "./components/OwnerRoute";
import PortalGate from "./components/PortalGate";
import PortalHome from "./pages/PortalHome";
import OwnerInventory from "./pages/OwnerInventory";
import OwnerOrders from "./pages/OwnerOrders";
import OwnerPrescriptions from "./pages/OwnerPrescriptions";
import OwnerAppointments from "./pages/OwnerAppointments";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Navbar />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<Home />} />

            <Route
              path="/portal"
              element={
                <PortalGate>
                  <PortalHome />
                </PortalGate>
              }
            />
            <Route
              path="/portal/login"
              element={
                <PortalGate>
                  <Login />
                </PortalGate>
              }
            />
            <Route
              path="/portal/register"
              element={
                <PortalGate>
                  <Register />
                </PortalGate>
              }
            />

            <Route
              path="/portal/admin/pharmacies"
              element={
                <PortalGate>
                  <AdminRoute>
                    <AdminPharmacies />
                  </AdminRoute>
                </PortalGate>
              }
            />

            <Route
              path="/portal/owner/inventory"
              element={
                <PortalGate>
                  <OwnerRoute>
                    <OwnerInventory />
                  </OwnerRoute>
                </PortalGate>
              }
            />
            <Route
              path="/portal/owner/orders"
              element={
                <PortalGate>
                  <OwnerRoute>
                    <OwnerOrders />
                  </OwnerRoute>
                </PortalGate>
              }
            />
            <Route
              path="/portal/owner/prescriptions"
              element={
                <PortalGate>
                  <OwnerRoute>
                    <OwnerPrescriptions />
                  </OwnerRoute>
                </PortalGate>
              }
            />
            <Route
              path="/portal/owner/appointments"
              element={
                <PortalGate>
                  <OwnerRoute>
                    <OwnerAppointments />
                  </OwnerRoute>
                </PortalGate>
              }
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
