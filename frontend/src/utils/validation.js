const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const E164_REGEX = /^\+[1-9]\d{1,14}$/;

export const isValidEmail = (value) => {
  if (typeof value !== "string") return false;
  return EMAIL_REGEX.test(value.trim());
};

export const isValidE164 = (value) => {
  if (typeof value !== "string") return false;
  return E164_REGEX.test(value.trim());
};

export const normalizeE164Input = (value) => {
  if (typeof value !== "string") return "";
  const trimmed = value.trim();
  if (!trimmed) return "";
  const hasPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/\D/g, "");
  return hasPlus ? `+${digits}` : digits;
};
