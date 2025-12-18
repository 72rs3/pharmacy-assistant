import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/axios";

export default function Register() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pharmacyName, setPharmacyName] = useState("");
  const [pharmacyDomain, setPharmacyDomain] = useState("");
  const [isOwner, setIsOwner] = useState(false);
  const navigate = useNavigate();

  const handleRegister = async (event) => {
    event.preventDefault();

    try {
      const endpoint = isOwner ? "/auth/register-owner" : "/auth/register";
      await api.post(endpoint, {
        email,
        password,
        full_name: fullName,
        pharmacy_name: isOwner ? pharmacyName : null,
        pharmacy_domain: isOwner ? pharmacyDomain || null : null,
      });
      alert("Account created successfully!");
      navigate("/login");
    } catch (error) {
      console.error(error.response?.data ?? error);
      alert("Registration failed!");
    }
  };

  return (
    <form onSubmit={handleRegister}>
      <h2>Register</h2>

      <label>
        <input
          type="checkbox"
          checked={isOwner}
          onChange={(event) => setIsOwner(event.target.checked)}
        />
        Registering as pharmacy owner
      </label>

      <input
        type="text"
        placeholder="Full name"
        value={fullName}
        onChange={(event) => setFullName(event.target.value)}
        required
      />

      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        required
      />

      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        required
      />

      {isOwner && (
        <>
          <input
            type="text"
            placeholder="Pharmacy name"
            value={pharmacyName}
            onChange={(event) => setPharmacyName(event.target.value)}
            required
          />
          <input
            type="text"
            placeholder="Pharmacy domain (optional, e.g. sunrise.local)"
            value={pharmacyDomain}
            onChange={(event) => setPharmacyDomain(event.target.value)}
          />
        </>
      )}

      <button type="submit">Register</button>
    </form>
  );
}
