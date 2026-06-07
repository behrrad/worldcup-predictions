import { auth } from "@clerk/nextjs/server";

import { apiFetch } from "./api";

/** Fetch the Django API from a Server Component, attaching the Clerk token. */
export async function serverFetch(path: string, opts: RequestInit = {}) {
  const { getToken } = await auth();
  const token = await getToken();
  return apiFetch(path, token, opts);
}
