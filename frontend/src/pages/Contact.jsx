import { useState } from "react";
import { Clock, Mail, MapPin, Phone } from "lucide-react";
import { useCustomerUi } from "../utils/customer-ui";
import { useTenant } from "../context/TenantContext";

export default function Contact() {
  const { pharmacy } = useTenant() ?? {};
  const { openChat } = useCustomerUi();
  const contactAddress =
    pharmacy?.contact_address ??
    "123 Health Avenue\nSuite 101\nWellness City, WC 12345";
  const contactPhone =
    pharmacy?.contact_phone ?? "Main: (555) 123-4567\nFax: (555) 123-4568\nEmergency: (555) 911-HELP";
  const contactEmail =
    pharmacy?.contact_email ?? "info@sunrpharmacy.com\nsupport@sunrpharmacy.com\nprescriptions@sunrpharmacy.com";
  const mapAddress = contactAddress.split("\n")[0] || "123 Health Avenue";
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    phone: "",
    subject: "",
    message: "",
  });

  const handleSubmit = (event) => {
    event.preventDefault();
    alert("Thank you for your message! We'll get back to you soon.");
    setFormData({ name: "", email: "", phone: "", subject: "", message: "" });
  };

  const handleChange = (event) => {
    setFormData((prev) => ({
      ...prev,
      [event.target.name]: event.target.value,
    }));
  };

  return (
    <div className="space-y-12">
      <section className="text-center space-y-4">
        <h1 className="text-5xl text-gray-900">Contact Us</h1>
        <p className="text-xl text-gray-600 max-w-3xl mx-auto">
          We're here to help. Reach out with any questions or concerns.
        </p>
      </section>

      <section className="grid md:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-md text-center">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <MapPin className="w-6 h-6 text-blue-600" />
          </div>
          <h3 className="text-gray-900 mb-2">Address</h3>
          <p className="text-gray-600 text-sm whitespace-pre-line">{contactAddress}</p>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-md text-center">
          <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Phone className="w-6 h-6 text-green-600" />
          </div>
          <h3 className="text-gray-900 mb-2">Phone</h3>
          <p className="text-gray-600 text-sm whitespace-pre-line">{contactPhone}</p>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-md text-center">
          <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Mail className="w-6 h-6 text-purple-600" />
          </div>
          <h3 className="text-gray-900 mb-2">Email</h3>
          <p className="text-gray-600 text-sm whitespace-pre-line">{contactEmail}</p>
        </div>

        <div className="bg-white p-6 rounded-xl shadow-md text-center">
          <div className="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Clock className="w-6 h-6 text-orange-600" />
          </div>
          <h3 className="text-gray-900 mb-2">Hours</h3>
          <p className="text-gray-600 text-sm">
            Mon-Fri: 9am - 7pm
            <br />
            Saturday: 10am - 5pm
            <br />
            Sunday: Closed
          </p>
        </div>
      </section>

      <section className="grid md:grid-cols-2 gap-8">
        <div className="bg-white rounded-2xl p-8 shadow-md">
          <h2 className="text-3xl text-gray-900 mb-6">Send us a Message</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="name" className="block text-sm text-gray-700 mb-2">
                Full Name *
              </label>
              <input
                type="text"
                id="name"
                name="name"
                value={formData.name}
                onChange={handleChange}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="John Doe"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm text-gray-700 mb-2">
                Email Address *
              </label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="john@example.com"
              />
            </div>

            <div>
              <label htmlFor="phone" className="block text-sm text-gray-700 mb-2">
                Phone Number
              </label>
              <input
                type="tel"
                id="phone"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="(555) 123-4567"
              />
            </div>

            <div>
              <label htmlFor="subject" className="block text-sm text-gray-700 mb-2">
                Subject *
              </label>
              <select
                id="subject"
                name="subject"
                value={formData.subject}
                onChange={handleChange}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
              >
                <option value="">Select a subject</option>
                <option value="prescription">Prescription Inquiry</option>
                <option value="delivery">Delivery Question</option>
                <option value="insurance">Insurance & Billing</option>
                <option value="general">General Question</option>
                <option value="feedback">Feedback</option>
              </select>
            </div>

            <div>
              <label htmlFor="message" className="block text-sm text-gray-700 mb-2">
                Message *
              </label>
              <textarea
                id="message"
                name="message"
                value={formData.message}
                onChange={handleChange}
                required
                rows={5}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="How can we help you?"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-[var(--brand-primary)] text-white rounded-lg hover:bg-[var(--brand-primary-600)] transition-colors"
            >
              Send Message
            </button>
          </form>
        </div>

        <div className="space-y-6">
          <div className="bg-gray-200 rounded-2xl h-96 flex items-center justify-center shadow-md">
            <div className="text-center text-gray-600">
              <MapPin className="w-16 h-16 mx-auto mb-4 text-gray-400" />
              <p>Interactive map would be displayed here</p>
              <p className="text-sm">{mapAddress}</p>
            </div>
          </div>

          <div className="bg-gradient-to-br from-[var(--brand-primary)] to-[var(--brand-primary-600)] rounded-2xl p-8 text-white">
            <h3 className="text-2xl mb-4">Need Immediate Assistance?</h3>
            <p className="mb-6 opacity-90">
              Our AI assistant is available 24/7 to answer your questions and help you find what you need.
            </p>
            <button
              type="button"
              onClick={openChat}
              className="w-full py-3 bg-white text-[var(--brand-primary)] rounded-lg hover:bg-gray-100 transition-colors"
            >
              Chat with AI Assistant Now
            </button>
          </div>
        </div>
      </section>

      <section className="bg-white rounded-2xl p-8 shadow-md">
        <h2 className="text-3xl text-gray-900 mb-8 text-center">Frequently Asked Questions</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h4 className="text-gray-900">Do you accept insurance?</h4>
            <p className="text-gray-600 text-sm">
              Yes, we accept most major insurance plans. Contact us to verify your coverage.
            </p>
          </div>
          <div className="space-y-3">
            <h4 className="text-gray-900">How long does prescription filling take?</h4>
            <p className="text-gray-600 text-sm">
              Most prescriptions are filled within 15-30 minutes. We also offer same-day service.
            </p>
          </div>
          <div className="space-y-3">
            <h4 className="text-gray-900">Do you offer delivery services?</h4>
            <p className="text-gray-600 text-sm">
              Yes. We offer free delivery for orders over $50 and same-day delivery is available.
            </p>
          </div>
          <div className="space-y-3">
            <h4 className="text-gray-900">Can I transfer my prescription?</h4>
            <p className="text-gray-600 text-sm">
              Absolutely. We make prescription transfers easy. Just provide your current pharmacy details.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
