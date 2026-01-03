import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import PortalShell from "./components/portal/PortalShell";
import PortalAuthLayout from "./components/portal/PortalAuthLayout";
import CustomerLayout from "./components/customer/CustomerLayout";
import Home from "./pages/Home";
import Shop from "./pages/Shop";
import Contact from "./pages/Contact";
import Appointments from "./pages/Appointments";
import CustomerOrders from "./pages/CustomerOrders";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AdminRoute from "./components/AdminRoute";
import AdminPharmacies from "./pages/AdminPharmacies";
import AdminAILogs from "./pages/AdminAILogs";
import OwnerRoute from "./components/OwnerRoute";
import PortalGate from "./components/PortalGate";
import PortalHome from "./pages/PortalHome";
import PortalSettings from "./pages/PortalSettings";
import OwnerInventory from "./pages/OwnerInventory";
import OwnerProducts from "./pages/OwnerProducts";
import OwnerOrders from "./pages/OwnerOrders";
import OwnerPrescriptions from "./pages/OwnerPrescriptions";
import OwnerAppointments from "./pages/OwnerAppointments";
import OwnerEscalations from "./pages/OwnerEscalations";
import OwnerInbox from "./pages/OwnerInbox";
import { isPortalHost } from "./utils/tenant";

export default function App() {
  const portal = isPortalHost();

  useEffect(() => {
    document.body.classList.toggle("portal-theme", portal);
    document.body.classList.toggle("customer-theme", !portal);
  }, [portal]);

  return (
    <BrowserRouter>
      {portal ? (
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/portal"
            element={
              <PortalGate>
                <PortalShell>
                  <PortalHome />
                </PortalShell>
              </PortalGate>
            }
          />
          <Route
            path="/portal/settings"
            element={
              <PortalGate>
                <PortalShell>
                  <PortalSettings />
                </PortalShell>
              </PortalGate>
            }
          />
          <Route
            path="/portal/login"
            element={
              <PortalGate>
                <PortalAuthLayout>
                  <Login />
                </PortalAuthLayout>
              </PortalGate>
            }
          />
          <Route
            path="/portal/register"
            element={
              <PortalGate>
                <PortalAuthLayout>
                  <Register />
                </PortalAuthLayout>
              </PortalGate>
            }
          />

          <Route
            path="/portal/admin/pharmacies"
            element={
              <PortalGate>
                <AdminRoute>
                  <PortalShell>
                    <AdminPharmacies />
                  </PortalShell>
                </AdminRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/admin/ai-logs"
            element={
              <PortalGate>
                <AdminRoute>
                  <PortalShell>
                    <AdminAILogs />
                  </PortalShell>
                </AdminRoute>
              </PortalGate>
            }
          />

          <Route
            path="/portal/owner/inventory"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerInventory />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/products"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerProducts />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/orders"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerOrders />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/prescriptions"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerPrescriptions />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/appointments"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerAppointments view="overview" />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/appointments/week"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerAppointments view="week" />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/appointments/schedule"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerAppointments view="schedule" />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/escalations"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerEscalations />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
          <Route
            path="/portal/owner/inbox"
            element={
              <PortalGate>
                <OwnerRoute>
                  <PortalShell>
                    <OwnerInbox />
                  </PortalShell>
                </OwnerRoute>
              </PortalGate>
            }
          />
        </Routes>
      ) : (
        <CustomerLayout>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/shop" element={<Shop />} />
            <Route path="/orders" element={<CustomerOrders />} />
            <Route path="/appointments" element={<Appointments />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </CustomerLayout>
      )}
    </BrowserRouter>
  );
}
