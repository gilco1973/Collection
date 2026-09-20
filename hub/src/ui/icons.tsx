import type { ReactNode } from "react";

/**
 * The ui-core icon set, as it appears in the artboards: a 16-unit viewBox,
 * 1.5 stroke, round caps. `Icon` reproduces the exact attribute set the
 * artboards carry so a live screen paints the same pixels as a generated one.
 */
type Props = { size?: number; className?: string; children: ReactNode; label?: string };

export function Icon({ size = 16, className = "i ", children, label }: Props) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      {children}
    </svg>
  );
}

export const Check = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="m3.5 8.5 3 3 6-7" />
  </Icon>
);
export const ArrowRight = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M3 8h10M9 4l4 4-4 4" />
  </Icon>
);
export const ArrowLeft = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M13 8H3M7 4 3 8l4 4" />
  </Icon>
);
export const Close = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="m4 4 8 8M12 4l-8 8" />
  </Icon>
);
export const Clock = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 5v3l2 1.5" />
  </Icon>
);
export const Grid = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M2.5 2.5h4.5v4.5H2.5zM9 2.5h4.5v4.5H9zM2.5 9h4.5v4.5H2.5zM9 9h4.5v4.5H9z" />
  </Icon>
);
export const OkCircle = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="m5.5 8 2 2 3.5-4" />
  </Icon>
);
export const Warn = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M8 2.5 14 13H2zM8 6.5v3M8 11.2v.3" />
  </Icon>
);
export const Info = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 7v4M8 5.2v.3" />
  </Icon>
);
export const Search = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="7" cy="7" r="4" />
    <path d="m10 10 3 3" />
  </Icon>
);
export const Bell = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M4 11V7a4 4 0 0 1 8 0v4l1 1.5H3zM6.5 14h3" />
  </Icon>
);
export const Layers = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M8 2 2 5l6 3 6-3zM2 8l6 3 6-3M2 11l6 3 6-3" />
  </Icon>
);
export const Plus = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M8 3v10M3 8h10" />
  </Icon>
);
export const Refresh = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M13 8a5 5 0 1 1-1.5-3.5M13 3v2.5h-2.5" />
  </Icon>
);

/* Listing glyphs, keyed by `ConsumerSummary.glyph`. */
export const Sparkle = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M8 2l1.2 3.8L13 7l-3.8 1.2L8 12l-1.2-3.8L3 7l3.8-1.2z" />
  </Icon>
);
export const Pulse = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M2 8h3l2-4 3 8 2-4h2" />
  </Icon>
);
export const Book = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M3 3h4a2 2 0 0 1 2 2v8a1.5 1.5 0 0 0-1.5-1.5H3zM13 3H9a2 2 0 0 0-2 2v8a1.5 1.5 0 0 1 1.5-1.5H13z" />
  </Icon>
);
export const Pen = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M11.5 2.5 13.5 4.5 6 12l-3 1 1-3z" />
  </Icon>
);
export const Chat = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M3 3h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5V11H3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
  </Icon>
);
export const Bolt = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M9 1.5 3 9h4.5L7 14.5 13 7H8.5z" />
  </Icon>
);
export const Shield = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M8 2 3 4v4c0 3 2.2 5 5 6 2.8-1 5-3 5-6V4z" />
  </Icon>
);
export const Play = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M5 3v10l8-5z" />
  </Icon>
);
export const Doc = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M4 1.5h5l3 3v10H4zM9 1.5v3h3M6 8h4M6 11h4" />
  </Icon>
);
export const Db = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <ellipse cx="8" cy="4" rx="5" ry="2" />
    <path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" />
  </Icon>
);
export const InfoCircle = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M8 7v4M8 5v.3" />
  </Icon>
);
export const Person = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="6" cy="5.5" r="2.2" />
    <path d="M1.5 13.5a4.5 4.5 0 0 1 9 0M10.5 3.5a2.2 2.2 0 0 1 0 4M11.5 9.5a4.5 4.5 0 0 1 3 4" />
  </Icon>
);
export const LinkIcon = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M6.5 9.5 9.5 6.5M7 4.5l1.3-1.3a2.5 2.5 0 0 1 3.5 3.5L10.5 8M9 11.5l-1.3 1.3a2.5 2.5 0 0 1-3.5-3.5L5.5 8" />
  </Icon>
);
export const Send = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <path d="M2 8 14 2l-3 12-3-5z" />
  </Icon>
);
export const Question = (p: Omit<Props, "children">) => (
  <Icon {...p}>
    <circle cx="8" cy="8" r="6" />
    <path d="M6.2 6.2a1.8 1.8 0 1 1 2.6 1.6c-.6.3-.8.7-.8 1.2M8 11.3v.2" />
  </Icon>
);

export type GlyphName = "sparkle" | "pulse" | "book" | "pen" | "chat" | "bolt" | "shield" | "layers";
export function Glyph({ name, size }: { name: GlyphName; size: number }) {
  switch (name) {
    case "sparkle":
      return <Sparkle size={size} />;
    case "pulse":
      return <Pulse size={size} />;
    case "book":
      return <Book size={size} />;
    case "pen":
      return <Pen size={size} />;
    case "chat":
      return <Chat size={size} />;
    case "bolt":
      return <Bolt size={size} />;
    case "shield":
      return <Shield size={size} />;
    case "layers":
      return <Layers size={size} />;
  }
}
