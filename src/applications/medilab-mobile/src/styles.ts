import { StyleSheet } from "react-native";

// Colours and shapes the screens share.
export const colors = {
  primary: "#1f6feb",
  text: "#1c2024",
  muted: "#60646c",
  border: "#d9d9e0",
  error: "#ce2c31",
};

export const styles = StyleSheet.create({
  screen: { flex: 1, padding: 24, gap: 16, justifyContent: "center" },
  title: { fontSize: 26, fontWeight: "600", color: colors.text },
  detail: { fontSize: 14, color: colors.muted },
  label: { fontSize: 14, fontWeight: "500", color: colors.text },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
    color: colors.text,
  },
  error: { fontSize: 14, color: colors.error },
  primaryButton: { backgroundColor: colors.primary, borderRadius: 8, paddingVertical: 12, alignItems: "center" },
  primaryButtonText: { color: "#ffffff", fontSize: 16, fontWeight: "600" },
  secondaryButton: {
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: "center",
  },
  secondaryButtonText: { color: colors.primary, fontSize: 16, fontWeight: "500" },
});
