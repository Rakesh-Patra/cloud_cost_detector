import { createClient } from "@insforge/sdk";

// Read environment variables loaded by Vite (prefixed with VITE_)
const baseUrl = import.meta.env.VITE_INSFORGE_PROJECT_URL || "https://mock.insforge.app";
const anonKey = import.meta.env.VITE_INSFORGE_ANON_KEY || "mock-anon-key";

export const insforge = createClient({
  baseUrl,
  anonKey,
});
