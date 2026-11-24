import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pin, PinOff, Plus } from "lucide-react";
import { useState } from "react";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Feedback } from "./entry-shared";

export function PhraseSuggestions({ onInsert }: { onInsert: (text: string) => void }) {
  const client = useQueryClient();
  const phrases = useQuery({
    queryKey: ["capture", "suggestions"],
    queryFn: api.captureSuggestions,
  });
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const pin = useMutation({
    mutationFn: ({ text, pinned }: { text: string; pinned: boolean }) =>
      pinned ? api.unpinPhrase(text) : api.pinPhrase(text),
    onSuccess: (items) => {
      client.setQueryData(["capture", "suggestions"], items);
      setText("");
      setAdding(false);
    },
  });
  return (
    <div className="phrase-suggestions">
      <div className="phrase-list" aria-label="常用词句">
        {phrases.data?.map((item) => (
          <span className={`phrase-chip ${item.pinned ? "phrase-pinned" : ""}`} key={item.text}>
            <button
              type="button"
              className="phrase-insert"
              onClick={() => onInsert(item.text)}
              title={`插入：${item.text}`}
            >
              {item.text}
            </button>
            <button
              type="button"
              className="phrase-pin"
              disabled={pin.isPending}
              aria-label={`${item.pinned ? "取消固定" : "固定"} ${item.text}`}
              title={item.pinned ? "取消固定" : "固定常用词"}
              onClick={() => pin.mutate(item)}
            >
              {item.pinned ? <PinOff size={13} /> : <Pin size={13} />}
            </button>
          </span>
        ))}
        <button
          className="phrase-add"
          type="button"
          onClick={() => setAdding(!adding)}
          aria-expanded={adding}
        >
          <Plus size={14} /> 固定词句
        </button>
      </div>
      {adding && (
        <div className="phrase-add-row">
          <Input
            aria-label="要固定的常用词句"
            placeholder="例：早上喝了豆浆"
            value={text}
            onChange={(event) => setText(event.target.value)}
            maxLength={80}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                if (text.trim() && !pin.isPending) pin.mutate({ text: text.trim(), pinned: false });
              }
            }}
          />
          <Button
            type="button"
            size="sm"
            disabled={!text.trim() || pin.isPending}
            onClick={() => pin.mutate({ text: text.trim(), pinned: false })}
          >
            固定
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>
            取消
          </Button>
        </div>
      )}
      <Feedback error={pin.error ?? phrases.error} />
    </div>
  );
}
