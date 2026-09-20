import type { ComponentType, SVGProps } from "react";
import type { JokerType } from "@/lib/types";
import { CloseIcon, HalfIcon, LockIcon, RouletteIcon, SkipIcon, StealIcon, SwapIcon } from "./Icons";

type SvgIcon = ComponentType<SVGProps<SVGSVGElement>>;

const jokerInfo: Record<JokerType, { name: string; description: string; icon: SvgIcon; tone: string; needsTarget: boolean }> = {
  gravity_roulette: { name: "Gravity Roulette", description: "Spin gravity to a random new direction.", icon: RouletteIcon, tone: "amber", needsTarget: false },
  fifty_fifty: { name: "The 50/50", description: "Erase half the pieces. Survivors settle.", icon: HalfIcon, tone: "red", needsTarget: false },
  skip: { name: "Skip", description: "Skip whoever is taking their turn.", icon: SkipIcon, tone: "blue", needsTarget: false },
  steal: { name: "Steal", description: "Turn one enemy piece into your color.", icon: StealIcon, tone: "green", needsTarget: true },
  swap: { name: "Swap", description: "Exchange two differently colored pieces.", icon: SwapIcon, tone: "cyan", needsTarget: true },
  gravity_lock: { name: "Gravity Lock", description: "Freeze natural gravity changes briefly.", icon: LockIcon, tone: "slate", needsTarget: false },
};

export function getJokerInfo(joker: JokerType) {
  return jokerInfo[joker];
}

interface JokerHandProps {
  jokers: JokerType[];
  selected: JokerType | null;
  pending: JokerType | null;
  disabled: boolean;
  onPlay: (joker: JokerType) => void;
  onCancel: () => void;
}

export default function JokerHand({ jokers, selected, pending, disabled, onPlay, onCancel }: JokerHandProps) {
  return (
    <section className="joker-hand" aria-label="Your private joker hand">
      <div className="hand-heading">
        <div><span className="eyebrow">Private hand</span><h2>Your Jokers</h2></div>
        {selected && <button className="cancel-selection" type="button" onClick={onCancel}><CloseIcon /> Cancel</button>}
      </div>
      {jokers.length === 0 ? (
        <div className="empty-hand">No jokers left. Win it the old-fashioned way.</div>
      ) : (
        <div className="joker-cards">
          {jokers.map((joker) => {
            const info = jokerInfo[joker];
            const Icon = info.icon;
            const isPending = pending === joker;
            const isSelected = selected === joker;
            return (
              <button
                key={joker}
                type="button"
                className={`joker-card joker-${info.tone}${isSelected ? " is-selected" : ""}`}
                disabled={disabled || pending !== null}
                onClick={() => onPlay(joker)}
                aria-pressed={isSelected}
              >
                <span className="joker-icon"><Icon /></span>
                <span className="joker-copy"><strong>{info.name}</strong><small>{isPending ? "Waiting for server…" : info.description}</small></span>
                <span className="joker-action">{isSelected ? "Selecting" : info.needsTarget ? "Choose" : "Play"}</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
