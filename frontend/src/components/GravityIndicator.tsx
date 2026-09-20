import type { GravityDirection } from "@/lib/types";
import { ArrowIcon, LockIcon } from "./Icons";

const labels: Record<GravityDirection, string> = {
  up: "Gravity up",
  down: "Gravity down",
  left: "Gravity left",
  right: "Gravity right",
};

export default function GravityIndicator({ direction, locked }: { direction: GravityDirection; locked: boolean }) {
  return (
    <div className={`gravity-indicator gravity-${direction}`} aria-live="polite">
      <span className="gravity-arrow"><ArrowIcon direction={direction} /></span>
      <span>{labels[direction]}</span>
      {locked && <span className="gravity-lock" title="Natural gravity changes are locked"><LockIcon /> Locked</span>}
    </div>
  );
}
