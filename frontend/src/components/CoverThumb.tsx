export function CoverThumb({
  src,
  alt,
  size = "md",
}: {
  src: string | null | undefined;
  alt: string;
  size?: "sm" | "md" | "lg" | "xl" | "fill";
}) {
  const className = `cover-thumb cover-thumb-${size}`;
  if (!src) {
    return <div className={`${className} cover-thumb-empty`} aria-hidden />;
  }
  return (
    <img
      className={className}
      src={src}
      alt={alt}
      loading="lazy"
      draggable={false}
    />
  );
}
