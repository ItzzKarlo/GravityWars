import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;
const base = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export function ArrowIcon({ direction = "right", ...props }: IconProps & { direction?: "up" | "down" | "left" | "right" }) {
  const turns = { right: 0, down: 90, left: 180, up: -90 }[direction];
  return <svg {...base} {...props} style={{ ...props.style, transform: `rotate(${turns}deg)` }}><path d="M5 12h14M14 7l5 5-5 5" /></svg>;
}

export function CopyIcon(props: IconProps) {
  return <svg {...base} {...props}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></svg>;
}

export function CheckIcon(props: IconProps) {
  return <svg {...base} {...props}><path d="m5 12 4 4L19 6" /></svg>;
}

export function EditIcon(props: IconProps) {
  return <svg {...base} {...props}><path d="M13.5 6.5 17.5 10.5M4 20l4.2-1 10.4-10.4a2.8 2.8 0 0 0-4-4L4.2 15 4 20Z" /></svg>;
}

export function LockIcon(props: IconProps) {
  return <svg {...base} {...props}><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>;
}

export function RouletteIcon(props: IconProps) {
  return <svg {...base} {...props}><circle cx="12" cy="12" r="8" /><path d="M12 4v4M12 16v4M4 12h4M16 12h4M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M17.7 6.3l-2.8 2.8M9.1 14.9l-2.8 2.8" /><circle cx="12" cy="12" r="2" /></svg>;
}

export function HalfIcon(props: IconProps) {
  return <svg {...base} {...props}><circle cx="12" cy="12" r="8" /><path d="M12 4v16M7.5 8.5l9 7M7.5 15.5l9-7" /></svg>;
}

export function SkipIcon(props: IconProps) {
  return <svg {...base} {...props}><path d="m5 5 10 7L5 19V5ZM18 5v14" /></svg>;
}

export function StealIcon(props: IconProps) {
  return <svg {...base} {...props}><circle cx="8" cy="12" r="4" /><circle cx="16" cy="12" r="4" /><path d="m13 7 3-3 3 3M16 4v5" /></svg>;
}

export function SwapIcon(props: IconProps) {
  return <svg {...base} {...props}><path d="M7 7h12l-3-3M17 17H5l3 3M19 7l-3 3M5 17l3-3" /></svg>;
}

export function CardsIcon(props: IconProps) {
  return <svg {...base} {...props}><rect x="7" y="4" width="11" height="16" rx="2" /><path d="m7 7-2 .5a2 2 0 0 0-1.4 2.4l2 7.5A2 2 0 0 0 7 19" /></svg>;
}

export function CloseIcon(props: IconProps) {
  return <svg {...base} {...props}><path d="m6 6 12 12M18 6 6 18" /></svg>;
}
