import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Routes that require an authenticated user.
const isProtected = createRouteMatcher([
  "/admin(.*)",
  "/dashboard(.*)",
  "/l/(.*)",
  "/leagues/(.*)",
]);

// Next.js 16 renamed Middleware -> Proxy; Clerk's middleware works as the default export.
export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next internals and static assets, run on everything else.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
