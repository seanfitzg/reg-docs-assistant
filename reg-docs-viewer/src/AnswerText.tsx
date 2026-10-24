import { Fragment, useState } from "react";
import type { RetrievedChunk } from "./api";

interface Props {
  answer: string;
  chunks: RetrievedChunk[];
}

export default function AnswerText({ answer, chunks }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const parts = answer.split(/(\[\d+\])/);
  const openChunk = open === null ? undefined : chunks[open - 1];

  return (
    <>
      <p className="answer">
        {parts.map((part, i) => {
          const match = /^\[(\d+)\]$/.exec(part);
          const number = match ? Number(match[1]) : 0;
          if (!match || !chunks[number - 1]) {
            return <Fragment key={i}>{part}</Fragment>;
          }
          return (
            <button
              key={i}
              type="button"
              className="marker"
              title={chunks[number - 1].text}
              onClick={() => setOpen(open === number ? null : number)}
            >
              {part}
            </button>
          );
        })}
      </p>
      {open !== null && openChunk && (
        <div className="chunk marker-chunk">
          <div className="mono">
            [{open}] {openChunk.chunk_id} - score {openChunk.score}
          </div>
          <p>{openChunk.text}</p>
        </div>
      )}
    </>
  );
}
