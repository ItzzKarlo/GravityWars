"use client";

import { useEffect, useRef, useState } from "react";
import type { Board, GravityDirection, JokerType, PlayerColor, Position } from "@/lib/types";
import GamePiece, { type VisualPiece } from "./GamePiece";
import { ArrowIcon, CloseIcon } from "./Icons";

interface GameBoardProps {
  board: Board;
  gravity: GravityDirection;
  canDrop: boolean;
  pendingDrop: boolean;
  selection: { joker: JokerType; targets: Position[] } | null;
  localColor: PlayerColor;
  onDrop: (lane: number) => void;
  onSelect: (position: Position) => void;
  onCancelSelection: () => void;
}

interface AnimatedPiece extends VisualPiece {
  targetRow?: number;
  targetColumn?: number;
}

const sourcePosition = (gravity: GravityDirection, row: number, column: number) => {
  if (gravity === "down") return { row: -1.15, column };
  if (gravity === "up") return { row: 7.15, column };
  if (gravity === "left") return { row, column: 7.15 };
  return { row, column: -1.15 };
};

function cells(board: Board) {
  return board.flatMap((row, rowIndex) => row.map((color, column) => ({ color, row: rowIndex, column }))).filter((cell): cell is { color: PlayerColor; row: number; column: number } => cell.color !== null);
}

function reconcile(previous: AnimatedPiece[], board: Board, gravity: GravityDirection, nextId: () => number): AnimatedPiece[] {
  const targets = cells(board);
  const unused = new Set(previous.map((piece) => piece.id));
  const result: AnimatedPiece[] = [];

  // The protocol has no piece IDs. Matching same-color pieces by minimum travel
  // preserves stable DOM identities across authoritative board snapshots.
  for (const target of targets) {
    const candidates = previous
      .filter((piece) => unused.has(piece.id) && piece.color === target.color)
      .sort((a, b) => {
        const distanceA = Math.abs(a.row - target.row) + Math.abs(a.column - target.column);
        const distanceB = Math.abs(b.row - target.row) + Math.abs(b.column - target.column);
        return distanceA - distanceB;
      });
    const match = candidates[0];
    if (match) {
      unused.delete(match.id);
      result.push({ ...match, row: target.row, column: target.column, entering: false });
    } else {
      const source = sourcePosition(gravity, target.row, target.column);
      result.push({ id: nextId(), color: target.color, ...source, entering: true, targetRow: target.row, targetColumn: target.column });
    }
  }
  return result;
}

function laneFull(board: Board, gravity: GravityDirection, lane: number) {
  if (gravity === "down") return board[0][lane] !== null;
  if (gravity === "up") return board[6][lane] !== null;
  if (gravity === "left") return board[lane][6] !== null;
  return board[lane][0] !== null;
}

function positionKey([row, column]: Position) {
  return `${row}-${column}`;
}

export default function GameBoard({ board, gravity, canDrop, pendingDrop, selection, localColor, onDrop, onSelect, onCancelSelection }: GameBoardProps) {
  const idRef = useRef(0);
  const [pieces, setPieces] = useState<AnimatedPiece[]>([]);

  useEffect(() => {
    setPieces((current) => reconcile(current, board, gravity, () => ++idRef.current));
    const frame = requestAnimationFrame(() => {
      setPieces((current) => current.map((piece) => {
        return piece.entering && piece.targetRow !== undefined && piece.targetColumn !== undefined
          ? { ...piece, row: piece.targetRow, column: piece.targetColumn, entering: false }
          : piece;
      }));
    });
    return () => cancelAnimationFrame(frame);
  }, [board, gravity]);

  const selectedKeys = new Set(selection?.targets.map(positionKey));
  const instruction = selection?.joker === "steal"
    ? "Choose an enemy piece to steal"
    : selection?.targets.length
      ? "Now choose a piece of another color"
      : "Choose the first piece to swap";

  const isValidTarget = (row: number, column: number) => {
    if (!selection) return false;
    const color = board[row][column];
    if (!color) return false;
    if (selection.joker === "steal") return color !== localColor;
    if (!selection.targets.length) return true;
    const [firstRow, firstColumn] = selection.targets[0];
    return (row !== firstRow || column !== firstColumn) && color !== board[firstRow][firstColumn];
  };

  const laneButtons = Array.from({ length: 7 }, (_, lane) => {
    const disabled = !canDrop || pendingDrop || laneFull(board, gravity, lane);
    return (
      <button
        key={lane}
        type="button"
        className={`lane-button lane-${gravity}`}
        style={gravity === "up" || gravity === "down" ? { left: `${lane * 100 / 7}%` } : { top: `${lane * 100 / 7}%` }}
        disabled={disabled}
        onClick={() => onDrop(lane)}
        aria-label={`Drop piece in ${gravity === "up" || gravity === "down" ? "column" : "row"} ${lane + 1}`}
      >
        <ArrowIcon direction={gravity} />
      </button>
    );
  });

  return (
    <div className="board-area">
      {selection && (
        <div className="selection-callout" role="status">
          <span>{instruction}</span>
          <button type="button" onClick={onCancelSelection} aria-label="Cancel selection"><CloseIcon /></button>
        </div>
      )}
      <div className={`game-board gravity-board-${gravity}${selection ? " selecting-target" : ""}`}>
        <div className="board-wells" aria-hidden="true">
          {Array.from({ length: 49 }, (_, index) => <span key={index} />)}
        </div>
        <div className="piece-layer" aria-hidden="true">
          {pieces.map((piece) => <GamePiece key={piece.id} piece={piece} />)}
        </div>
        {selection ? (
          <div className="target-grid">
            {board.map((row, rowIndex) => row.map((_, column) => {
              const position: Position = [rowIndex, column];
              const selected = selectedKeys.has(positionKey(position));
              const valid = isValidTarget(rowIndex, column);
              return (
                <button
                  key={`${rowIndex}-${column}`}
                  type="button"
                  className={`${valid ? "valid-target" : ""}${selected ? " selected-target" : ""}`}
                  disabled={!valid}
                  onClick={() => onSelect(position)}
                  aria-label={valid ? `Select piece at row ${rowIndex + 1}, column ${column + 1}` : undefined}
                />
              );
            }))}
          </div>
        ) : (
          <div className="lane-layer">{laneButtons}</div>
        )}
      </div>
    </div>
  );
}
