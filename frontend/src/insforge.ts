import { createClient } from "@insforge/sdk";

/**
 * InsForge (Supabase-compatible) client configuration.
 *
 * SECURITY: No credential fallbacks are used here.
 * Hardcoded credentials leak into the compiled JS bundle and are visible
 * to any user who inspects network responses or the dist/ directory.
 *
 * Required environment variables (defined in frontend/.env, never committed):
 *   VITE_INSFORGE_PROJECT_URL — The InsForge project base URL
 *   VITE_INSFORGE_ANON_KEY    — The InsForge anonymous/public API key
 *
 * See frontend/.env.example for the expected format.
 */
const baseUrl = (import.meta.env.VITE_INSFORGE_PROJECT_URL as string | undefined) || "";
const anonKey = (import.meta.env.VITE_INSFORGE_ANON_KEY as string | undefined) || "";

export const insforge = createClient({ baseUrl, anonKey });

