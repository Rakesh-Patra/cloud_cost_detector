import { createClient } from "@insforge/sdk";

// Read environment variables loaded by Vite (prefixed with VITE_)
const baseUrl = import.meta.env.VITE_INSFORGE_PROJECT_URL || "https://scf29qqy.us-east.insforge.app";
const anonKey = import.meta.env.VITE_INSFORGE_ANON_KEY || "ik_fc877384331b6eaae45d762900f67d0c"; // gitleaks:allow

export const insforge = createClient({
  baseUrl,
  anonKey,
});
