/**
 * Profile picture. Shows the uploaded image, or a colored initial as a
 * fallback when the player hasn't set one. Safe to use in Server Components
 * (no hooks). A plain <img> is used on purpose — avatars come from arbitrary
 * Supabase Storage URLs, so we skip next/image's remote-pattern config.
 */
export default function Avatar({
  src,
  name,
  size = 48,
}: {
  src: string | null;
  name: string;
  size?: number;
}) {
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className="avatar"
        src={src}
        alt={name}
        width={size}
        height={size}
        style={{ width: size, height: size }}
      />
    );
  }
  const initial = (name || "؟").trim().charAt(0).toUpperCase();
  return (
    <span
      className="avatar avatar-fallback"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      aria-label={name}
    >
      {initial}
    </span>
  );
}
