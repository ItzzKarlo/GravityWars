import type { CSSProperties } from "react";
import type { PlayerColor } from "@/lib/types";

export interface VisualPiece {
  id: number;
  color: PlayerColor;
  row: number;
  column: number;
  entering?: boolean;
}

export default function GamePiece({ piece }: { piece: VisualPiece }) {
  const style = {
    "--piece-row": piece.row,
    "--piece-column": piece.column,
  } as CSSProperties;

  return (
    <div
      className={`game-piece piece-${piece.color}${piece.entering ? " piece-entering" : ""}`}
      style={style}
      aria-hidden="true"
    >
      <span className="piece-shine" />
    </div>
  );
}
